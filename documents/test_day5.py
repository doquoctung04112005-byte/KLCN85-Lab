from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Department, UserProfile

from .models import Document


class DayFiveDocumentAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department_a = Department.objects.create(code="DAY5-A", name="Phòng A")
        cls.department_b = Department.objects.create(code="DAY5-B", name="Phòng B")

        def make_user(username, role, department, **user_fields):
            user = get_user_model().objects.create_user(
                username=username,
                password="TestPass123!",
                **user_fields,
            )
            UserProfile.objects.create(user=user, role=role, department=department)
            return user

        cls.a1 = make_user("nhanvien_a1", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.a2 = make_user("nhanvien_a2", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.head_a = make_user(
            "truongphong_a", UserProfile.Role.DEPARTMENT_HEAD, cls.department_a
        )
        cls.b1 = make_user("nhanvien_b1", UserProfile.Role.EMPLOYEE, cls.department_b)
        cls.admin = make_user("business_admin", UserProfile.Role.ADMIN, None)
        cls.inactive = make_user(
            "inactive_user",
            UserProfile.Role.EMPLOYEE,
            cls.department_b,
            is_active=False,
        )
        cls.no_profile = get_user_model().objects.create_user(
            username="superuser_without_profile",
            password="TestPass123!",
            is_staff=True,
            is_superuser=True,
        )

        cls.a1_document = Document.objects.create(
            title="Document A1",
            content="Private content A1",
            owner=cls.a1,
            department=cls.department_a,
        )
        cls.a2_document = Document.objects.create(
            title="Document A2",
            content="Private content A2",
            owner=cls.a2,
            department=cls.department_a,
        )
        cls.head_document = Document.objects.create(
            title="Document head A",
            content="Private content head A",
            owner=cls.head_a,
            department=cls.department_a,
        )
        cls.b1_document = Document.objects.create(
            title="Document B1",
            content="Private content B1",
            owner=cls.b1,
            department=cls.department_b,
        )
        cls.all_documents = (
            cls.a1_document,
            cls.a2_document,
            cls.head_document,
            cls.b1_document,
        )

    @staticmethod
    def detail_url(document):
        return reverse("document_detail", kwargs={"pk": document.pk})

    @staticmethod
    def edit_url(document):
        return reverse("document_edit", kwargs={"pk": document.pk})

    @staticmethod
    def delete_url(document):
        return reverse("document_delete", kwargs={"pk": document.pk})

    def test_list_detail_and_edit_follow_the_same_role_policy(self):
        cases = (
            (self.a1, (self.a1_document,), (self.a1_document,)),
            (self.a2, (self.a2_document,), (self.a2_document,)),
            (
                self.head_a,
                (self.a1_document, self.a2_document, self.head_document),
                (self.head_document,),
            ),
            (self.b1, (self.b1_document,), (self.b1_document,)),
            (self.admin, self.all_documents, self.all_documents),
            (self.no_profile, (), ()),
        )
        for user, visible, editable in cases:
            with self.subTest(username=user.username):
                self.client.force_login(user)
                list_response = self.client.get(reverse("document_list"))
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    {document.pk for document in list_response.context["documents"]},
                    {document.pk for document in visible},
                )

                for document in self.all_documents:
                    detail = self.client.get(self.detail_url(document))
                    edit = self.client.get(self.edit_url(document))
                    if document in visible:
                        self.assertEqual(detail.status_code, 200)
                        self.assertContains(detail, document.content)
                        self.assertEqual(
                            edit.status_code, 200 if document in editable else 403
                        )
                    else:
                        self.assertEqual(detail.status_code, 404)
                        self.assertEqual(edit.status_code, 404)
                        self.assertNotIn(document.content, detail.content.decode())
                        self.assertNotIn(document.content, edit.content.decode())
                self.client.logout()

    def test_non_admin_get_and_post_delete_are_denied_without_deleting(self):
        cases = (
            (self.a1, self.a1_document),
            (self.a2, self.a2_document),
            (self.head_a, self.head_document),
            (self.head_a, self.a2_document),
            (self.b1, self.b1_document),
            (self.no_profile, self.a1_document),
        )
        for user, document in cases:
            with self.subTest(username=user.username, document=document.pk):
                self.client.force_login(user)
                for method in ("get", "post"):
                    with self.subTest(method=method):
                        if method == "get":
                            response = self.client.get(self.delete_url(document))
                        else:
                            response = self.client.post(
                                self.delete_url(document),
                                {"role": UserProfile.Role.ADMIN},
                            )
                        self.assertEqual(response.status_code, 403)
                        self.assertNotIn(document.content, response.content.decode())
                        preserved = Document.objects.get(pk=document.pk)
                        self.assertEqual(preserved.title, document.title)
                        self.assertEqual(preserved.content, document.content)
                self.client.logout()

    def test_admin_confirmation_get_is_safe_and_csrf_post_deletes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        delete_url = self.delete_url(self.a2_document)

        confirmation = client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, self.a2_document.title)
        self.assertContains(confirmation, 'name="csrfmiddlewaretoken"')
        self.assertTrue(Document.objects.filter(pk=self.a2_document.pk).exists())

        without_csrf = client.post(delete_url)
        self.assertEqual(without_csrf.status_code, 403)
        self.assertTrue(Document.objects.filter(pk=self.a2_document.pk).exists())

        csrf_token = client.cookies["csrftoken"].value
        deleted = client.post(delete_url, {"csrfmiddlewaretoken": csrf_token})
        self.assertRedirects(deleted, reverse("document_list"))
        self.assertFalse(Document.objects.filter(pk=self.a2_document.pk).exists())

    def test_anonymous_requests_redirect_to_login_without_deleting(self):
        delete_url = self.delete_url(self.a1_document)
        user_list_url = reverse("user_list")
        for url, method in (
            (delete_url, "get"),
            (delete_url, "post"),
            (user_list_url, "get"),
        ):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )
        self.assertTrue(Document.objects.filter(pk=self.a1_document.pk).exists())

    def test_user_list_shows_only_required_fields_to_profile_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 200)

        for username in (
            self.a1.username,
            self.a2.username,
            self.head_a.username,
            self.b1.username,
            self.admin.username,
            self.inactive.username,
            self.no_profile.username,
        ):
            with self.subTest(username=username):
                self.assertContains(response, username)

        for label in (
            "Tên đăng nhập",
            "Vai trò",
            "Phòng ban",
            "Trạng thái",
            "Nhân viên",
            "Trưởng phòng",
            "Quản trị viên",
            "Phòng A",
            "Phòng B",
            "Hoạt động",
            "Không hoạt động",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)

        for user in (
            self.a1,
            self.a2,
            self.head_a,
            self.b1,
            self.admin,
            self.inactive,
            self.no_profile,
        ):
            self.assertNotContains(response, user.password)
        self.assertNotContains(response, "TestPass123!")
        self.assertNotContains(response, "Mật khẩu")

    def test_user_list_rejects_all_non_admin_roles_and_missing_profile(self):
        for user in (self.a1, self.a2, self.head_a, self.b1, self.no_profile):
            with self.subTest(username=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("user_list"))
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.admin.username, response.content.decode())
                self.client.logout()

    def test_admin_navigation_has_user_list_and_delete_links_only_for_admin(self):
        user_list_url = reverse("user_list")
        delete_url = self.delete_url(self.a1_document)

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard")), user_list_url)
        self.assertContains(self.client.get(self.detail_url(self.a1_document)), delete_url)
        self.client.logout()

        self.client.force_login(self.a1)
        self.assertNotContains(self.client.get(reverse("dashboard")), user_list_url)
        self.assertNotContains(self.client.get(self.detail_url(self.a1_document)), delete_url)
        self.client.logout()

        self.client.force_login(self.head_a)
        self.assertNotContains(self.client.get(reverse("dashboard")), user_list_url)
        self.assertNotContains(self.client.get(self.detail_url(self.a1_document)), delete_url)

