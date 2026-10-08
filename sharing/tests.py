from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, UserProfile
from documents.models import Document

from .models import DocumentShare


class DocumentSharingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department_a = Department.objects.create(code="SHARE-A", name="Phòng A")
        cls.department_b = Department.objects.create(code="SHARE-B", name="Phòng B")

        def make_user(username, role, department):
            user = get_user_model().objects.create_user(username=username)
            UserProfile.objects.create(user=user, role=role, department=department)
            return user

        cls.owner = make_user(
            "share_owner", UserProfile.Role.EMPLOYEE, cls.department_a
        )
        cls.recipient = make_user(
            "share_recipient", UserProfile.Role.EMPLOYEE, cls.department_a
        )
        cls.department_head = make_user(
            "share_head", UserProfile.Role.DEPARTMENT_HEAD, cls.department_a
        )
        cls.other_department_user = make_user(
            "share_other_department", UserProfile.Role.EMPLOYEE, cls.department_b
        )
        cls.recipient_b = make_user(
            "share_recipient_b", UserProfile.Role.EMPLOYEE, cls.department_b
        )
        cls.admin = make_user("share_admin", UserProfile.Role.ADMIN, None)

        cls.document = Document.objects.create(
            title="Shared document A",
            content="Content owned by A",
            owner=cls.owner,
            department=cls.department_a,
        )
        cls.document_b = Document.objects.create(
            title="Shared document B",
            content="Content owned by B",
            owner=cls.other_department_user,
            department=cls.department_b,
        )

    @staticmethod
    def manage_url(document):
        return reverse("document_share_manage", kwargs={"document_pk": document.pk})

    @staticmethod
    def revoke_url(share):
        return reverse("document_share_revoke", kwargs={"share_pk": share.pk})

    @staticmethod
    def share_data(recipient, permission=DocumentShare.Permission.VIEW, expires_at=None):
        expires_at = expires_at or timezone.localtime(
            timezone.now() + timedelta(days=2)
        )
        return {
            "recipient": recipient.pk,
            "permission": permission,
            "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M"),
        }

    def create_share(
        self,
        *,
        granted_by=None,
        recipient=None,
        document=None,
        permission=DocumentShare.Permission.VIEW,
        expires_at=None,
        revoked_at=None,
    ):
        return DocumentShare.objects.create(
            document=document or self.document,
            granted_by=granted_by or self.owner,
            recipient=recipient or self.recipient,
            permission=permission,
            expires_at=expires_at or timezone.now() + timedelta(days=2),
            revoked_at=revoked_at,
        )

    def test_owner_grants_view_and_recipient_cannot_edit(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = self.manage_url(self.document)

        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentShare.objects.count(), 0)

        no_csrf = client.post(url, self.share_data(self.recipient))
        self.assertEqual(no_csrf.status_code, 403)
        self.assertEqual(DocumentShare.objects.count(), 0)

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            url,
            {**self.share_data(self.recipient), "csrfmiddlewaretoken": csrf_token},
        )
        self.assertRedirects(response, url)
        share = DocumentShare.objects.get()
        self.assertEqual(share.granted_by, self.owner)
        self.assertEqual(share.recipient, self.recipient)
        self.assertEqual(share.permission, DocumentShare.Permission.VIEW)
        self.assertIsNotNone(share.expires_at)

        self.client.force_login(self.recipient)
        listing = self.client.get(reverse("document_list"))
        self.assertContains(listing, self.document.title)
        self.assertContains(
            self.client.get(reverse("document_detail", kwargs={"pk": self.document.pk})),
            self.document.content,
        )
        edit = self.client.get(reverse("document_edit", kwargs={"pk": self.document.pk}))
        self.assertEqual(edit.status_code, 403)

    def test_edit_share_allows_recipient_to_edit_through_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.manage_url(self.document),
            self.share_data(self.recipient, DocumentShare.Permission.EDIT),
        )
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.recipient)
        edit_url = reverse("document_edit", kwargs={"pk": self.document.pk})
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        response = self.client.post(
            edit_url,
            {"title": "Edited by recipient", "content": "Updated through active share"},
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.title, "Edited by recipient")
        self.assertEqual(self.document.content, "Updated through active share")

    def test_expired_share_does_not_grant_list_detail_or_edit_access(self):
        self.create_share(
            permission=DocumentShare.Permission.EDIT,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_login(self.recipient)

        listing = self.client.get(reverse("document_list"))
        self.assertNotContains(listing, self.document.title)
        for name in ("document_detail", "document_edit"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, kwargs={"pk": self.document.pk}))
                self.assertEqual(response.status_code, 404)

    def test_share_requires_a_future_expiration(self):
        self.client.force_login(self.owner)
        data = self.share_data(self.recipient)
        data.pop("expires_at")
        response = self.client.post(self.manage_url(self.document), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentShare.objects.count(), 0)

        response = self.client.post(
            self.manage_url(self.document),
            self.share_data(
                self.recipient,
                expires_at=timezone.localtime(timezone.now() - timedelta(days=1)),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentShare.objects.count(), 0)

    def test_owner_can_revoke_with_post_and_csrf_and_access_ends(self):
        share = self.create_share(permission=DocumentShare.Permission.EDIT)
        revoke_url = self.revoke_url(share)

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.get(revoke_url).status_code, 405)
        share.refresh_from_db()
        self.assertIsNone(share.revoked_at)

        manage_url = self.manage_url(self.document)
        client.get(manage_url)
        no_csrf = client.post(revoke_url)
        self.assertEqual(no_csrf.status_code, 403)
        share.refresh_from_db()
        self.assertIsNone(share.revoked_at)

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(revoke_url, {"csrfmiddlewaretoken": csrf_token})
        self.assertRedirects(response, manage_url)
        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)

        self.client.force_login(self.recipient)
        listing = self.client.get(reverse("document_list"))
        self.assertNotContains(listing, self.document.title)
        for name in ("document_detail", "document_edit"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, kwargs={"pk": self.document.pk}))
                self.assertEqual(response.status_code, 404)

    def test_owner_and_admin_cannot_share_with_other_department(self):
        for user in (self.owner, self.admin):
            with self.subTest(grantor=user.username):
                self.client.force_login(user)
                response = self.client.post(
                    self.manage_url(self.document),
                    self.share_data(self.other_department_user),
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(DocumentShare.objects.count(), 0)
                self.client.logout()

    def test_admin_can_share_any_document_to_its_department(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.manage_url(self.document_b),
            self.share_data(self.recipient_b, DocumentShare.Permission.EDIT),
        )
        self.assertEqual(response.status_code, 302)
        share = DocumentShare.objects.get()
        self.assertEqual(share.document, self.document_b)
        self.assertEqual(share.granted_by, self.admin)

        self.client.force_login(self.recipient_b)
        self.assertContains(
            self.client.get(reverse("document_detail", kwargs={"pk": self.document_b.pk})),
            self.document_b.content,
        )
        self.assertEqual(
            self.client.get(reverse("document_edit", kwargs={"pk": self.document_b.pk})).status_code,
            200,
        )

    def test_non_owner_cannot_grant_a_share(self):
        self.client.force_login(self.recipient)
        response = self.client.post(
            self.manage_url(self.document),
            self.share_data(self.department_head),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DocumentShare.objects.count(), 0)

    def test_admin_can_revoke_another_users_grant(self):
        share = self.create_share(granted_by=self.owner)
        self.client.force_login(self.admin)
        response = self.client.post(self.revoke_url(share))
        self.assertRedirects(response, self.manage_url(self.document))
        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)

    def test_non_grantor_cannot_revoke_and_department_head_keeps_base_access(self):
        share = self.create_share(
            recipient=self.department_head,
            permission=DocumentShare.Permission.VIEW,
        )
        self.client.force_login(self.recipient)
        response = self.client.post(self.revoke_url(share))
        self.assertEqual(response.status_code, 403)
        share.refresh_from_db()
        self.assertIsNone(share.revoked_at)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.revoke_url(share)).status_code, 302)

        self.client.force_login(self.department_head)
        listing = self.client.get(reverse("document_list"))
        self.assertContains(listing, self.document.title)
        detail = self.client.get(
            reverse("document_detail", kwargs={"pk": self.document.pk})
        )
        self.assertContains(detail, self.document.content)
        self.assertEqual(
            self.client.get(reverse("document_edit", kwargs={"pk": self.document.pk})).status_code,
            403,
        )
