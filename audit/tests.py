import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, UserProfile
from documents.models import Document
from documents.services import save_document_attachment
from sharing.models import DocumentShare

from .services import record_event
from .models import AuditLog


class AuditEventFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="AUD-A", name="Audit A")
        cls.other_department = Department.objects.create(code="AUD-B", name="Audit B")
        cls.owner = get_user_model().objects.create_user(
            username="audit_owner",
            password="AuditTestPassword-DoNotLog!",
        )
        UserProfile.objects.create(
            user=cls.owner,
            role=UserProfile.Role.EMPLOYEE,
            department=cls.department,
        )
        cls.recipient = get_user_model().objects.create_user(username="audit_recipient")
        UserProfile.objects.create(
            user=cls.recipient,
            role=UserProfile.Role.EMPLOYEE,
            department=cls.department,
        )
        cls.outsider = get_user_model().objects.create_user(username="audit_outsider")
        UserProfile.objects.create(
            user=cls.outsider,
            role=UserProfile.Role.EMPLOYEE,
            department=cls.other_department,
        )
        cls.document = Document.objects.create(
            title="Audit private title",
            content="Audit private body that must not appear in logs",
            owner=cls.owner,
            department=cls.department,
        )

    def attach_pdf(self):
        attachment = save_document_attachment(
            self.document,
            SimpleUploadedFile("audit-private.pdf", b"%PDF-1.7\nprivate data"),
        )
        self.addCleanup(attachment.file.storage.delete, attachment.file.name)
        return attachment

    def event(self, action, result=None):
        events = AuditLog.objects.filter(
            actor=self.owner,
            action=action,
            object_id=str(self.document.pk),
        )
        if result:
            events = events.filter(result=result)
        return events

    def test_test_runner_routes_jsonl_events_away_from_live_web_log(self):
        configured_path = Path(settings.AUDIT_LOG_FILE).resolve()
        live_path = (Path(settings.BASE_DIR) / "logs" / "audit.jsonl").resolve()
        self.assertNotEqual(configured_path, live_path)

        live_stat = live_path.stat() if live_path.exists() else None
        record_event(
            actor=self.owner,
            action="test.isolation",
            object_type="test",
            object_id="audit-log-isolation",
            result="success",
        )

        self.assertTrue(configured_path.is_file())
        self.assertEqual(live_path.stat() if live_path.exists() else None, live_stat)

    def test_login_success_and_failure_are_recorded_without_credentials(self):
        login_url = reverse("login")
        success = self.client.post(
            login_url,
            {"username": self.owner.username, "password": "AuditTestPassword-DoNotLog!"},
        )
        self.assertEqual(success.status_code, 302)
        successful_events = AuditLog.objects.filter(
            action="login.success", actor=self.owner
        )
        self.assertEqual(successful_events.count(), 1)
        self.assertEqual(successful_events.get().result, "success")

        self.client.logout()
        failure = self.client.post(
            login_url,
            {"username": self.owner.username, "password": "AuditWrongPassword-DoNotLog!"},
        )
        self.assertEqual(failure.status_code, 200)
        failed_event = AuditLog.objects.get(action="login.failure")
        self.assertIsNone(failed_event.actor)
        self.assertEqual(failed_event.result, "denied")
        self.assertEqual(failed_event.details, {})

        log_text = settings.AUDIT_LOG_FILE.read_text(encoding="utf-8")
        log_rows = [json.loads(line) for line in log_text.splitlines() if line.strip()]
        self.assertEqual(log_rows[-2]["action"], "login.success")
        self.assertEqual(log_rows[-1]["action"], "login.failure")
        self.assertNotIn("AuditTestPassword-DoNotLog!", log_text)
        self.assertNotIn("AuditWrongPassword-DoNotLog!", log_text)

    def test_allowed_document_view_preview_and_download_are_recorded_once(self):
        self.attach_pdf()
        self.client.force_login(self.owner)

        detail = self.client.get(reverse("document_detail", kwargs={"pk": self.document.pk}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.event("document.view", "allowed").count(), 1)

        preview = self.client.get(reverse("document_preview", kwargs={"pk": self.document.pk}))
        self.assertEqual(preview.status_code, 200)
        self.addCleanup(preview._resource_closers[0])
        self.assertEqual(self.event("document.preview", "allowed").count(), 1)

        download = self.client.get(reverse("document_download", kwargs={"pk": self.document.pk}))
        self.assertEqual(download.status_code, 200)
        self.addCleanup(download._resource_closers[0])
        self.assertEqual(self.event("document.download", "allowed").count(), 1)
        log_text = settings.AUDIT_LOG_FILE.read_text(encoding="utf-8")
        self.assertNotIn(self.document.title, log_text)
        self.assertNotIn(self.document.content, log_text)
        self.assertNotIn("audit-private.pdf", log_text)

    def test_direct_document_idor_is_allowed_but_sharing_is_denied(self):
        self.attach_pdf()
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("document_detail", kwargs={"pk": self.document.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.outsider,
                action="document.view",
                object_id=str(self.document.pk),
                result="allowed",
            ).count(),
            1,
        )

        response = self.client.get(reverse("document_download", kwargs={"pk": self.document.pk}))
        self.assertEqual(response.status_code, 200)
        self.addCleanup(response._resource_closers[0])
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.outsider,
                action="document.download",
                object_id=str(self.document.pk),
                result="allowed",
            ).count(),
            1,
        )

        share_manage_url = reverse(
            "document_share_manage", kwargs={"document_pk": self.document.pk}
        )
        response = self.client.get(share_manage_url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.outsider,
                action="sharing.manage",
                object_id=str(self.document.pk),
                result="denied",
            ).count(),
            1,
        )

        log_text = settings.AUDIT_LOG_FILE.read_text(encoding="utf-8")
        self.assertNotIn(self.document.content, log_text)
        self.assertNotIn(self.document.title, log_text)

    def test_grant_revoke_and_invalid_grant_have_correct_single_events(self):
        self.client.force_login(self.owner)
        manage_url = reverse(
            "document_share_manage", kwargs={"document_pk": self.document.pk}
        )
        invalid = self.client.post(manage_url, {})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(self.event("sharing.grant").count(), 0)
        self.assertEqual(DocumentShare.objects.count(), 0)

        expires_at = timezone.localtime(timezone.now() + timedelta(days=1))
        grant = self.client.post(
            manage_url,
            {
                "recipient": self.recipient.pk,
                "permission": DocumentShare.Permission.VIEW,
                "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(grant.status_code, 302)
        share = DocumentShare.objects.get()
        self.assertEqual(self.event("sharing.grant", "success").count(), 1)

        revoke = self.client.post(
            reverse("document_share_revoke", kwargs={"share_pk": share.pk})
        )
        self.assertEqual(revoke.status_code, 302)
        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)
        self.assertEqual(self.event("sharing.revoke", "success").count(), 1)

        self.client.force_login(self.outsider)
        denied_revoke = self.client.post(
            reverse("document_share_revoke", kwargs={"share_pk": share.pk})
        )
        self.assertEqual(denied_revoke.status_code, 403)
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.outsider,
                action="sharing.revoke",
                object_id=str(self.document.pk),
                result="denied",
            ).count(),
            1,
        )
