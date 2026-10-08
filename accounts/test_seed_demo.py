import os
import runpy
import secrets
from pathlib import Path
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from documents.models import Document

from .models import Department, UserProfile


class SeedDemoCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.demo_password = secrets.token_urlsafe(24)

    expected_profiles = {
        "nhanvien_a1": (UserProfile.Role.EMPLOYEE, "A"),
        "nhanvien_a2": (UserProfile.Role.EMPLOYEE, "A"),
        "truongphong_a": (UserProfile.Role.DEPARTMENT_HEAD, "A"),
        "nhanvien_b1": (UserProfile.Role.EMPLOYEE, "B"),
        "admin_demo": (UserProfile.Role.ADMIN, None),
    }
    expected_documents = {
        UUID("11111111-1111-4111-8111-111111111111"): ("nhanvien_a1", "A"),
        UUID("22222222-2222-4222-8222-222222222222"): ("nhanvien_a2", "A"),
        UUID("33333333-3333-4333-8333-333333333333"): ("nhanvien_b1", "B"),
    }

    def seed(self, stdout):
        with patch.dict(os.environ, {"KLCN85_DEMO_PASSWORD": self.demo_password}):
            call_command("seed_demo", stdout=stdout)

    def assert_seeded_records(self):
        self.assertEqual(Department.objects.count(), 2)
        self.assertEqual(Department.objects.get(code="A").name, "Phòng A")
        self.assertEqual(Department.objects.get(code="B").name, "Phòng B")

        user_model = get_user_model()
        self.assertEqual(user_model.objects.count(), 5)
        self.assertEqual(UserProfile.objects.count(), 5)
        self.assertEqual(
            set(user_model.objects.values_list("username", flat=True)),
            set(self.expected_profiles),
        )
        for username, (role, department_code) in self.expected_profiles.items():
            with self.subTest(username=username):
                user = user_model.objects.get(username=username)
                profile = UserProfile.objects.select_related("department").get(user=user)
                self.assertEqual(profile.role, role)
                self.assertEqual(
                    profile.department.code if profile.department else None,
                    department_code,
                )
                self.assertTrue(user.is_active)

        self.assertGreaterEqual(Document.objects.count(), 3)
        for document_id, (owner_name, department_code) in self.expected_documents.items():
            with self.subTest(document_id=document_id):
                document = Document.objects.select_related("owner", "department").get(
                    pk=document_id
                )
                self.assertEqual(document.owner.username, owner_name)
                self.assertEqual(document.department.code, department_code)
                self.assertTrue(document.title)
                self.assertTrue(document.content)

    def test_seed_twice_keeps_fixed_documents_and_existing_password(self):
        output = StringIO()
        self.seed(output)
        self.assert_seeded_records()
        self.assertNotIn(self.demo_password, output.getvalue())

        user_model = get_user_model()
        for username in self.expected_profiles:
            with self.subTest(username=username):
                self.assertTrue(
                    user_model.objects.get(username=username).check_password(
                        self.demo_password
                    )
                )

        first_document_ids = set(Document.objects.values_list("pk", flat=True))
        first_counts = (
            Department.objects.count(),
            user_model.objects.count(),
            UserProfile.objects.count(),
            Document.objects.count(),
        )

        a1 = user_model.objects.get(username="nhanvien_a1")
        changed_password = secrets.token_urlsafe(24)
        while changed_password == self.demo_password:
            changed_password = secrets.token_urlsafe(24)
        a1.set_password(changed_password)
        a1.save(update_fields=["password"])
        changed_password_hash = a1.password

        self.seed(output)
        self.assert_seeded_records()
        self.assertEqual(
            first_counts,
            (
                Department.objects.count(),
                user_model.objects.count(),
                UserProfile.objects.count(),
                Document.objects.count(),
            ),
        )
        self.assertEqual(
            set(Document.objects.values_list("pk", flat=True)),
            first_document_ids,
        )
        a1.refresh_from_db()
        self.assertEqual(a1.password, changed_password_hash)
        self.assertTrue(a1.check_password(changed_password))
        self.assertFalse(a1.check_password(self.demo_password))
        self.assertNotIn(self.demo_password, output.getvalue())

    def test_missing_password_fails_before_writing_records(self):
        output = StringIO()
        with patch.dict(os.environ):
            os.environ.pop("KLCN85_DEMO_PASSWORD", None)
            with self.assertRaises(CommandError) as error:
                call_command("seed_demo", stdout=output)

        self.assertIn("KLCN85_DEMO_PASSWORD", str(error.exception))
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(UserProfile.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)
        self.assertNotIn(self.demo_password, output.getvalue())


class PostgresDatabaseSettingsTests(SimpleTestCase):
    settings_file = Path(__file__).resolve().parents[1] / "config" / "settings.py"

    def test_postgresql_connection_settings(self):
        test_password = "test-only-db-password"
        with patch.dict(os.environ, {"KLCN85_DB_PASSWORD": test_password}):
            values = runpy.run_path(str(self.settings_file))

        self.assertEqual(
            values["DATABASES"]["default"],
            {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "klcn85_lab",
                "USER": "klcn85_app",
                "PASSWORD": test_password,
                "HOST": "127.0.0.1",
                "PORT": "5432",
            },
        )


