from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, UserProfile
from sharing.models import DocumentShare

from .models import Document, DocumentAttachment, DocumentFolder
from .services import save_document_attachment
from .validators import MAX_DOCUMENT_UPLOAD_SIZE, validate_document_upload


class DocumentFileAndFolderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department_a = Department.objects.create(code="FILES-A", name="Phòng A")
        cls.department_b = Department.objects.create(code="FILES-B", name="Phòng B")

        def make_user(username, role, department):
            user = get_user_model().objects.create_user(username=username)
            UserProfile.objects.create(user=user, role=role, department=department)
            return user

        cls.owner = make_user("files_owner", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.recipient = make_user("files_recipient", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.head = make_user("files_head", UserProfile.Role.DEPARTMENT_HEAD, cls.department_a)
        cls.other_owner = make_user("files_other", UserProfile.Role.EMPLOYEE, cls.department_a)
        cls.other_department_user = make_user(
            "files_b", UserProfile.Role.EMPLOYEE, cls.department_b
        )
        cls.admin = make_user("files_admin", UserProfile.Role.ADMIN, None)

        cls.document = Document.objects.create(
            title="Owned document",
            content="Existing text content",
            owner=cls.owner,
            department=cls.department_a,
        )
        cls.other_document = Document.objects.create(
            title="Private needle document",
            content="Private department B content",
            owner=cls.other_department_user,
            department=cls.department_b,
        )

    def track_attachment(self, attachment):
        self.addCleanup(attachment.file.storage.delete, attachment.file.name)

    def track_response_file(self, response):
        self.addCleanup(response._resource_closers[0])

    def attach_pdf(self, document=None):
        attachment = save_document_attachment(
            document or self.document,
            SimpleUploadedFile("private-report.pdf", b"%PDF-1.7\nprivate data", content_type="application/pdf"),
        )
        self.track_attachment(attachment)
        return attachment

    @staticmethod
    def office_zip(extension):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            if extension == ".docx":
                archive.writestr(
                    "word/document.xml",
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body><w:p><w:r><w:t>Word preview sample</w:t></w:r></w:p></w:body></w:document>",
                )
            else:
                archive.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    '<sheets><sheet name="Summary" sheetId="1" r:id="rId1"/></sheets></workbook>',
                )
                archive.writestr(
                    "xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                    "</Relationships>",
                )
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Excel preview sample</t>'
                    "</is></c></row></sheetData></worksheet>",
                )
        return buffer.getvalue()

    def test_validator_accepts_supported_types_and_rejects_mismatch_and_oversize(self):
        supported = (
            ("report.pdf", b"%PDF-1.7\n"),
            ("image.png", b"\x89PNG\r\n\x1a\n"),
            ("image.jpg", b"\xff\xd8\xff\xe0"),
            ("image.jpeg", b"\xff\xd8\xff\xe0"),
            ("file.docx", self.office_zip(".docx")),
            ("file.xlsx", self.office_zip(".xlsx")),
        )
        for filename, content in supported:
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(filename, content)
                self.assertIsNone(validate_document_upload(upload))

        invalid = SimpleUploadedFile("renamed.pdf", b"not a PDF")
        with self.assertRaisesMessage(ValidationError, "Nội dung tệp không khớp"):
            validate_document_upload(invalid)

        unsupported = SimpleUploadedFile("notes.txt", b"plain text")
        with self.assertRaisesMessage(ValidationError, "Chỉ chấp nhận tệp"):
            validate_document_upload(unsupported)

        oversized = SimpleUploadedFile("large.pdf", b"x" * (MAX_DOCUMENT_UPLOAD_SIZE + 1))
        with self.assertRaisesMessage(ValidationError, "vượt quá giới hạn 20 MB"):
            validate_document_upload(oversized)

    def test_upload_saves_metadata_under_private_random_name_and_supports_download_preview(self):
        self.client.force_login(self.owner)
        contents = b"%PDF-1.7\nactual upload"
        response = self.client.post(
            reverse("document_create"),
            {
                "title": "Uploaded PDF",
                "content": "",
                "upload": SimpleUploadedFile("original.pdf", contents),
            },
        )
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(title="Uploaded PDF")
        attachment = document.attachment
        self.track_attachment(attachment)
        self.assertEqual(attachment.display_name, "original.pdf")
        self.assertEqual(attachment.file_type, "pdf")
        self.assertEqual(attachment.file_size, len(contents))
        self.assertNotEqual(attachment.file.name, "original.pdf")
        self.assertNotIn("original.pdf", attachment.file.name)
        self.assertIsNone(attachment.file.storage.base_url)
        with self.assertRaisesMessage(ValueError, "no public URL"):
            attachment.file.url
        self.assertIn("private_uploads", attachment.file.path)

        download = self.client.get(reverse("document_download", kwargs={"pk": document.pk}))
        self.assertEqual(download.status_code, 200)
        self.track_response_file(download)
        self.assertIn("attachment", download["Content-Disposition"])

        preview = self.client.get(reverse("document_preview", kwargs={"pk": document.pk}))
        self.assertEqual(preview.status_code, 200)
        self.track_response_file(preview)
        self.assertEqual(preview["Content-Type"], "application/pdf")
        self.assertIn("inline", preview["Content-Disposition"])

    def test_invalid_upload_shows_clear_error_and_keeps_existing_data(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("document_create"),
            {
                "title": "Invalid upload",
                "content": "",
                "upload": SimpleUploadedFile("spoofed.pdf", b"not a PDF"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nội dung tệp không khớp với loại PDF")
        self.assertFalse(Document.objects.filter(title="Invalid upload").exists())

        self.document.refresh_from_db()
        self.assertEqual(self.document.content, "Existing text content")

    def test_active_share_allows_download_but_expired_revoked_and_other_user_do_not(self):
        self.attach_pdf()
        download_url = reverse("document_download", kwargs={"pk": self.document.pk})
        preview_url = reverse("document_preview", kwargs={"pk": self.document.pk})

        self.client.force_login(self.other_department_user)
        self.assertEqual(self.client.get(download_url).status_code, 404)
        self.assertEqual(self.client.get(preview_url).status_code, 404)

        share = DocumentShare.objects.create(
            document=self.document,
            granted_by=self.owner,
            recipient=self.recipient,
            permission=DocumentShare.Permission.VIEW,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.recipient)
        download = self.client.get(download_url)
        self.assertEqual(download.status_code, 200)
        self.track_response_file(download)
        preview = self.client.get(preview_url)
        self.assertEqual(preview.status_code, 200)
        self.track_response_file(preview)

        share.expires_at = timezone.now() - timedelta(seconds=1)
        share.save(update_fields=["expires_at"])
        self.assertEqual(self.client.get(download_url).status_code, 404)

        share.expires_at = timezone.now() + timedelta(days=1)
        share.revoked_at = timezone.now()
        share.save(update_fields=["expires_at", "revoked_at"])
        self.assertEqual(self.client.get(download_url).status_code, 404)
        self.assertEqual(self.client.get(preview_url).status_code, 404)

    def test_image_and_office_previews_are_inline_and_recheck_view_permissions(self):
        image = save_document_attachment(
            self.document,
            SimpleUploadedFile("photo.png", b"\x89PNG\r\n\x1a\nimage data"),
        )
        self.track_attachment(image)
        self.client.force_login(self.owner)
        preview_url = reverse("document_preview", kwargs={"pk": self.document.pk})
        response = self.client.get(preview_url)
        self.assertEqual(response.status_code, 200)
        self.track_response_file(response)
        self.assertEqual(response["Content-Type"], "image/png")

        office_document = Document.objects.create(
            title="Office file",
            content="",
            owner=self.owner,
            department=self.department_a,
        )
        office = save_document_attachment(
            office_document,
            SimpleUploadedFile("sheet.xlsx", self.office_zip(".xlsx")),
        )
        self.track_attachment(office)
        office_preview = self.client.get(
            reverse("document_preview", kwargs={"pk": office_document.pk})
        )
        self.assertEqual(office_preview.status_code, 200)
        self.assertEqual(office_preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(office_preview, "Excel preview sample")

        word_document = Document.objects.create(
            title="Word file",
            content="",
            owner=self.owner,
            department=self.department_a,
        )
        word = save_document_attachment(
            word_document,
            SimpleUploadedFile("report.docx", self.office_zip(".docx")),
        )
        self.track_attachment(word)
        word_preview_url = reverse("document_preview", kwargs={"pk": word_document.pk})
        self.assertContains(self.client.get(word_preview_url), "Word preview sample")

        self.client.force_login(self.other_department_user)
        self.assertEqual(self.client.get(word_preview_url).status_code, 404)
        self.client.force_login(self.recipient)
        self.assertEqual(self.client.get(word_preview_url).status_code, 404)
        share = DocumentShare.objects.create(
            document=word_document,
            granted_by=self.owner,
            recipient=self.recipient,
            permission=DocumentShare.Permission.VIEW,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertContains(self.client.get(word_preview_url), "Word preview sample")
        share.expires_at = timezone.now() - timedelta(seconds=1)
        share.save(update_fields=["expires_at"])
        self.assertEqual(self.client.get(word_preview_url).status_code, 404)
        share.expires_at = timezone.now() + timedelta(days=1)
        share.revoked_at = timezone.now()
        share.save(update_fields=["expires_at", "revoked_at"])
        self.assertEqual(self.client.get(word_preview_url).status_code, 404)

    def test_folder_creation_assigns_identity_and_department_and_opens_child_path(self):
        self.client.force_login(self.owner)
        create_url = reverse("folder_create")
        response = self.client.post(
            create_url,
            {
                "name": "Parent",
                "owner": self.other_owner.pk,
                "department": self.department_b.pk,
            },
        )
        self.assertRedirects(response, reverse("folder_list"))
        parent = DocumentFolder.objects.get(name="Parent")
        self.assertEqual(parent.owner, self.owner)
        self.assertEqual(parent.department, self.department_a)
        self.assertEqual(set(self.client.get(create_url).context["form"].fields), {"name", "parent"})

        response = self.client.post(
            create_url,
            {"name": "Child", "parent": parent.pk},
        )
        self.assertRedirects(
            response,
            reverse("folder_detail", kwargs={"folder_pk": parent.pk}),
        )
        child = DocumentFolder.objects.get(name="Child")
        self.assertEqual(child.owner, self.owner)
        self.assertEqual(child.department, self.department_a)
        self.assertEqual(child.parent, parent)

        opened = self.client.get(reverse("folder_detail", kwargs={"folder_pk": child.pk}))
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.context["ancestors"], [parent])

    def test_folder_cannot_move_into_itself_or_descendant_and_foreign_folder_is_hidden(self):
        parent = DocumentFolder.objects.create(
            name="Parent",
            owner=self.owner,
            department=self.department_a,
        )
        child = DocumentFolder.objects.create(
            name="Child",
            owner=self.owner,
            department=self.department_a,
            parent=parent,
        )
        foreign_folder = DocumentFolder.objects.create(
            name="Foreign",
            owner=self.other_department_user,
            department=self.department_b,
        )
        self.client.force_login(self.owner)

        manage_url = reverse("folder_manage", kwargs={"folder_pk": parent.pk})
        response = self.client.post(manage_url, {"name": "Parent", "parent": child.pk})
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent_id)
        self.assertEqual(
            self.client.get(
                reverse("folder_detail", kwargs={"folder_pk": foreign_folder.pk})
            ).status_code,
            404,
        )

        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(
                reverse("folder_detail", kwargs={"folder_pk": foreign_folder.pk})
            ).status_code,
            200,
        )

        response = self.client.post(
            reverse("folder_manage", kwargs={"folder_pk": foreign_folder.pk}),
            {"name": "Renamed", "parent": ""},
        )
        self.assertEqual(response.status_code, 302)
        foreign_folder.refresh_from_db()
        self.assertEqual(foreign_folder.name, "Renamed")

    def test_document_move_requires_owner_or_admin_and_matching_folder_owner_and_department(self):
        owner_folder = DocumentFolder.objects.create(
            name="Owned folder", owner=self.owner, department=self.department_a
        )
        same_department_other_owner_folder = DocumentFolder.objects.create(
            name="Other owner's folder",
            owner=self.other_owner,
            department=self.department_a,
        )
        other_department_folder = DocumentFolder.objects.create(
            name="Other department folder",
            owner=self.other_department_user,
            department=self.department_b,
        )
        self.client.force_login(self.owner)
        edit_url = reverse("document_edit", kwargs={"pk": self.document.pk})
        response = self.client.post(
            edit_url,
            {"title": self.document.title, "content": self.document.content, "folder": owner_folder.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.folder, owner_folder)

        for folder in (same_department_other_owner_folder, other_department_folder):
            with self.subTest(folder=folder.name):
                response = self.client.post(
                    edit_url,
                    {"title": self.document.title, "content": self.document.content, "folder": folder.pk},
                )
                self.assertEqual(response.status_code, 200)
                self.document.refresh_from_db()
                self.assertEqual(self.document.folder, owner_folder)

        share = DocumentShare.objects.create(
            document=self.document,
            granted_by=self.owner,
            recipient=self.recipient,
            permission=DocumentShare.Permission.EDIT,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.recipient)
        response = self.client.post(
            edit_url,
            {
                "title": "Edited with share",
                "content": self.document.content,
                "folder": other_department_folder.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.folder, owner_folder)
        self.assertEqual(
            self.client.get(reverse("document_delete", kwargs={"pk": self.document.pk})).status_code,
            403,
        )

    def test_folder_does_not_grant_document_access_and_search_only_filters_visible_documents(self):
        private_folder = DocumentFolder.objects.create(
            name="Private folder",
            owner=self.other_department_user,
            department=self.department_b,
        )
        self.other_document.folder = private_folder
        self.other_document.save(update_fields=["folder"])

        self.client.force_login(self.owner)
        folder_response = self.client.get(
            reverse("folder_detail", kwargs={"folder_pk": private_folder.pk})
        )
        self.assertEqual(folder_response.status_code, 404)
        search_response = self.client.get(
            reverse("document_list"), {"scope": "all", "q": "Private needle"}
        )
        self.assertNotContains(search_response, self.other_document.title)
        self.assertEqual(list(search_response.context["documents"]), [])

        share = DocumentShare.objects.create(
            document=self.document,
            granted_by=self.owner,
            recipient=self.recipient,
            permission=DocumentShare.Permission.VIEW,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.recipient)
        shared = self.client.get(
            reverse("document_list"), {"scope": "shared", "q": self.document.title}
        )
        self.assertEqual(
            [document.pk for document in shared.context["documents"]],
            [self.document.pk],
        )
        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at"])
        shared = self.client.get(
            reverse("document_list"), {"scope": "shared", "q": self.document.title}
        )
        self.assertEqual(list(shared.context["documents"]), [])
