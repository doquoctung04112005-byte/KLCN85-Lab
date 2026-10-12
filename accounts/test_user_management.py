from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from accounts.models import Department, UserProfile
from documents.models import Document
from sharing.models import DocumentShare


class AccountManagementFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department_a = Department.objects.create(code="MGT-A", name="Phòng A")
        cls.department_b = Department.objects.create(code="MGT-B", name="Phòng B")

        cls.admin = get_user_model().objects.create_user(username="manager_admin")
        UserProfile.objects.create(
            user=cls.admin,
            role=UserProfile.Role.ADMIN,
            department=None,
        )
        cls.employee = get_user_model().objects.create_user(
            username="managed_employee",
            password="ManagedUserPassword-940!",
        )
        UserProfile.objects.create(
            user=cls.employee,
            role=UserProfile.Role.EMPLOYEE,
            department=cls.department_a,
        )
        cls.department_head = get_user_model().objects.create_user(
            username="managed_head"
        )
        UserProfile.objects.create(
            user=cls.department_head,
            role=UserProfile.Role.DEPARTMENT_HEAD,
            department=cls.department_a,
        )
        cls.user_without_profile = get_user_model().objects.create_user(
            username="managed_missing_profile"
        )

    @staticmethod
    def create_url():
        return reverse("user_create")

    @staticmethod
    def edit_url(user):
        return reverse("user_edit", kwargs={"user_pk": user.pk})

    def update_data(self, *, role=None, department=None, is_active=True, **extra):
        return {
            "role": role or UserProfile.Role.EMPLOYEE,
            "department": department.pk if department else "",
            "is_active": "true" if is_active else "false",
            **extra,
        }

    def create_data(self, **extra):
        return {
            "username": "new_managed_user",
            "password1": "Strong-Passphrase-940!",
            "password2": "Strong-Passphrase-940!",
            "role": UserProfile.Role.EMPLOYEE,
            "department": self.department_a.pk,
            **extra,
        }

    def test_application_admin_can_create_user_and_profile_atomically(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.create_url(), self.create_data())
        self.assertRedirects(response, reverse("user_list"))

        created = get_user_model().objects.get(username="new_managed_user")
        self.assertTrue(created.check_password("Strong-Passphrase-940!"))
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertEqual(created.profile.role, UserProfile.Role.EMPLOYEE)
        self.assertEqual(created.profile.department, self.department_a)
        self.assertEqual(UserProfile.objects.filter(user=created).count(), 1)
        event = AuditLog.objects.get(action="account.create", object_id=str(created.pk))
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.result, "success")
        self.assertEqual(event.details, {})
        self.assertNotIn(
            "Strong-Passphrase-940!",
            settings.AUDIT_LOG_FILE.read_text(encoding="utf-8"),
        )

        app_admin_response = self.client.post(
            self.create_url(),
            self.create_data(
                username="profile_admin_only",
                role=UserProfile.Role.ADMIN,
                department="",
            ),
        )
        self.assertRedirects(app_admin_response, reverse("user_list"))
        app_admin = get_user_model().objects.get(username="profile_admin_only")
        self.assertEqual(app_admin.profile.role, UserProfile.Role.ADMIN)
        self.assertFalse(app_admin.is_staff)
        self.assertFalse(app_admin.is_superuser)

    def test_create_checks_duplicate_username_passwords_and_django_password_validators(self):
        self.client.force_login(self.admin)
        duplicate = self.client.post(
            self.create_url(),
            self.create_data(username=self.employee.username),
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(get_user_model().objects.filter(username=self.employee.username).count(), 1)

        mismatch = self.client.post(
            self.create_url(),
            self.create_data(password2="Different-Passphrase-123!"),
        )
        self.assertEqual(mismatch.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="new_managed_user").exists())

        weak_password = self.client.post(
            self.create_url(),
            self.create_data(
                password1="123",
                password2="123",
                username="weak_password_user",
            ),
        )
        self.assertEqual(weak_password.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="weak_password_user").exists())

    def test_privileged_django_fields_are_rejected_on_create_and_update(self):
        self.client.force_login(self.admin)
        create = self.client.post(
            self.create_url(),
            self.create_data(is_superuser="true", is_staff="true"),
        )
        self.assertEqual(create.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="new_managed_user").exists())
        self.assertNotIn("is_superuser", create.context["form"].fields)
        self.assertNotIn("is_staff", create.context["form"].fields)

        update = self.client.post(
            self.edit_url(self.employee),
            self.update_data(is_superuser="true", is_staff="true"),
        )
        self.assertEqual(update.status_code, 200)
        self.employee.refresh_from_db()
        self.employee.profile.refresh_from_db()
        self.assertFalse(self.employee.is_superuser)
        self.assertFalse(self.employee.is_staff)
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)
        self.assertNotIn("is_superuser", update.context["form"].fields)

    def test_admin_can_update_role_department_and_status_with_one_audit_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.edit_url(self.employee),
            self.update_data(
                role=UserProfile.Role.DEPARTMENT_HEAD,
                department=self.department_a,
                is_active=False,
            ),
        )
        self.assertRedirects(response, reverse("user_list"))
        self.employee.refresh_from_db()
        self.employee.profile.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertEqual(self.employee.profile.role, UserProfile.Role.DEPARTMENT_HEAD)
        self.assertEqual(self.employee.profile.department, self.department_a)
        self.assertEqual(UserProfile.objects.filter(user=self.employee).count(), 1)

        event = AuditLog.objects.get(action="account.lock", object_id=str(self.employee.pk))
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(
            event.details,
            {"changed_fields": ["role", "is_active"]},
        )

    def test_role_and_department_change_are_audited_without_moving_old_documents(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.edit_url(self.employee),
            self.update_data(
                role=UserProfile.Role.DEPARTMENT_HEAD,
                department=self.department_b,
                is_active=True,
            ),
        )
        self.assertRedirects(response, reverse("user_list"))
        event = AuditLog.objects.get(
            action="account.update",
            object_id=str(self.employee.pk),
        )
        self.assertEqual(
            event.details,
            {"changed_fields": ["role", "department"]},
        )
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.department, self.department_b)

    def test_lock_unlock_events_and_locked_user_cannot_log_in(self):
        self.client.force_login(self.admin)
        self.client.post(
            self.edit_url(self.employee),
            self.update_data(department=self.department_a, is_active=False),
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="account.lock",
                object_id=str(self.employee.pk),
                result="success",
            ).exists()
        )

        self.client.post(
            self.edit_url(self.employee),
            self.update_data(department=self.department_a, is_active=True),
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="account.unlock",
                object_id=str(self.employee.pk),
                result="success",
            ).exists()
        )

        self.client.post(
            self.edit_url(self.employee),
            self.update_data(department=self.department_a, is_active=False),
        )
        self.client.logout()
        login = self.client.post(
            reverse("login"),
            {
                "username": self.employee.username,
                "password": "ManagedUserPassword-940!",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_employee_can_self_promote_to_application_admin_in_lab(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assertEqual(client.get(reverse("user_list")).status_code, 200)

        self_edit_url = self.edit_url(self.employee)
        form_page = client.get(self_edit_url)
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, 'name="role"')
        csrf_token = client.cookies["csrftoken"].value

        payload = self.update_data(
            role=UserProfile.Role.ADMIN,
            department=self.department_b,
            is_active=False,
        )
        without_csrf = client.post(self_edit_url, payload)
        self.assertEqual(without_csrf.status_code, 403)
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)

        response = client.post(
            self_edit_url,
            {**payload, "csrfmiddlewaretoken": csrf_token},
        )
        self.assertRedirects(response, reverse("profile"))

        self.employee.refresh_from_db()
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.role, UserProfile.Role.ADMIN)
        self.assertEqual(self.employee.profile.department, self.department_a)
        self.assertTrue(self.employee.is_active)
        self.assertFalse(self.employee.is_staff)
        self.assertFalse(self.employee.is_superuser)
        self.assertEqual(client.get(reverse("user_list")).status_code, 200)
        self.assertEqual(client.get(self.create_url()).status_code, 200)
        event = AuditLog.objects.get(
            actor=self.employee,
            action="account.update",
            object_id=str(self.employee.pk),
            result="success",
        )
        self.assertEqual(event.details, {"changed_fields": ["role"]})

    def test_non_admin_get_and_post_are_denied_for_create_and_others_edit(self):
        for user, target in (
            (self.employee, self.department_head),
            (self.department_head, self.employee),
        ):
            with self.subTest(username=user.username):
                self.client.force_login(user)
                for url in (self.create_url(), self.edit_url(target)):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(
                        self.client.post(url, self.create_data()).status_code,
                        403,
                    )
                self.client.logout()

        self.client.force_login(self.department_head)
        self.assertEqual(self.client.get(self.edit_url(self.department_head)).status_code, 403)
        self.client.logout()

        self.assertFalse(
            get_user_model().objects.filter(username="new_managed_user").exists()
        )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.department_head,
                action__in=("account.create", "account.update"),
                result="denied",
            ).count(),
            5,
        )

    def test_anonymous_cannot_open_or_post_account_management_urls(self):
        create_url = self.create_url()
        edit_url = self.edit_url(self.employee)
        for url, data in (
            (create_url, self.create_data()),
            (edit_url, self.update_data(is_active=False)),
        ):
            with self.subTest(url=url):
                for method in ("get", "post"):
                    response = getattr(self.client, method)(
                        url,
                        data if method == "post" else None,
                    )
                    self.assertRedirects(
                        response,
                        f"{reverse('login')}?next={url}",
                        fetch_redirect_response=False,
                    )
        self.assertFalse(
            get_user_model().objects.filter(username="new_managed_user").exists()
        )
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_django_superuser_without_application_admin_role_is_denied(self):
        django_superuser = get_user_model().objects.create_superuser(
            username="django_superuser_only",
            password="DjangoSuperuserPassword-940!",
        )
        UserProfile.objects.create(
            user=django_superuser,
            role=UserProfile.Role.EMPLOYEE,
            department=self.department_a,
        )
        self.client.force_login(django_superuser)
        self.assertEqual(self.client.get(self.create_url()).status_code, 403)
        self.assertEqual(
            self.client.post(self.edit_url(self.employee), {}).status_code,
            403,
        )

    def test_admin_cannot_lock_self_or_remove_last_active_application_admin(self):
        self.client.force_login(self.admin)
        self_locked = self.client.post(
            self.edit_url(self.admin),
            self.update_data(role=UserProfile.Role.ADMIN, is_active=False),
        )
        self.assertEqual(self_locked.status_code, 200)
        self.assertTrue(self.admin.is_active)

        demoted = self.client.post(
            self.edit_url(self.admin),
            self.update_data(role=UserProfile.Role.EMPLOYEE, is_active=True),
        )
        self.assertEqual(demoted.status_code, 200)
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, UserProfile.Role.ADMIN)
        self.assertEqual(
            UserProfile.objects.filter(
                role=UserProfile.Role.ADMIN,
                user__is_active=True,
            ).count(),
            1,
        )

    def test_department_change_is_blocked_when_documents_or_shares_conflict(self):
        owned_document = Document.objects.create(
            title="Existing owned document",
            content="",
            owner=self.employee,
            department=self.department_a,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            self.edit_url(self.employee),
            self.update_data(department=self.department_b),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "đang sở hữu 1 tài liệu")
        self.employee.profile.refresh_from_db()
        owned_document.refresh_from_db()
        self.assertEqual(self.employee.profile.department, self.department_a)
        self.assertEqual(owned_document.department, self.department_a)

        recipient_document = Document.objects.create(
            title="Shared document",
            content="",
            owner=self.admin,
            department=self.department_a,
        )
        DocumentShare.objects.create(
            document=recipient_document,
            granted_by=self.admin,
            recipient=self.employee,
            permission=DocumentShare.Permission.VIEW,
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.post(
            self.edit_url(self.employee),
            self.update_data(department=self.department_b),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "liên quan đến 1 lượt chia sẻ")
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.department, self.department_a)

    def test_editing_user_without_profile_creates_exactly_one_profile(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.edit_url(self.user_without_profile),
            self.update_data(department=self.department_b),
        )
        self.assertRedirects(response, reverse("user_list"))
        self.assertEqual(
            UserProfile.objects.filter(user=self.user_without_profile).count(), 1
        )
        self.assertEqual(
            self.user_without_profile.profile.department,
            self.department_b,
        )

    def test_account_forms_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.create_url(), self.create_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="new_managed_user").exists())

        client.get(self.create_url())
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            self.create_url(),
            {**self.create_data(), "csrfmiddlewaretoken": csrf_token},
        )
        self.assertRedirects(response, reverse("user_list"))
