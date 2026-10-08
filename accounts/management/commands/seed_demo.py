import os
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Department, UserProfile
from documents.models import Document


DEPARTMENTS = (
    ("A", "Phòng A"),
    ("B", "Phòng B"),
)

ACCOUNTS = (
    ("nhanvien_a1", UserProfile.Role.EMPLOYEE, "A"),
    ("nhanvien_a2", UserProfile.Role.EMPLOYEE, "A"),
    ("truongphong_a", UserProfile.Role.DEPARTMENT_HEAD, "A"),
    ("nhanvien_b1", UserProfile.Role.EMPLOYEE, "B"),
    ("admin_demo", UserProfile.Role.ADMIN, None),
)

DOCUMENTS = (
    (
        UUID("11111111-1111-4111-8111-111111111111"),
        "Tài liệu mẫu A1",
        "Nội dung mẫu do nhân viên A1 sở hữu.",
        "nhanvien_a1",
        "A",
    ),
    (
        UUID("22222222-2222-4222-8222-222222222222"),
        "Tài liệu mẫu A2",
        "Nội dung mẫu do nhân viên A2 sở hữu.",
        "nhanvien_a2",
        "A",
    ),
    (
        UUID("33333333-3333-4333-8333-333333333333"),
        "Tài liệu mẫu B1",
        "Nội dung mẫu do nhân viên B1 sở hữu.",
        "nhanvien_b1",
        "B",
    ),
)


class Command(BaseCommand):
    help = "Tạo phòng ban, tài khoản và tài liệu mẫu có mã cố định."

    def handle(self, *args, **options):
        password = os.environ.get("KLCN85_DEMO_PASSWORD")
        if not password or not password.strip():
            raise CommandError(
                "Chưa đặt KLCN85_DEMO_PASSWORD. Hãy đặt biến môi trường này trước khi chạy seed_demo."
            )

        user_model = get_user_model()
        with transaction.atomic():
            departments = {}
            for code, name in DEPARTMENTS:
                department, _ = Department.objects.update_or_create(
                    code=code,
                    defaults={"name": name},
                )
                departments[code] = department

            users = {}
            for username, role, department_code in ACCOUNTS:
                user, created = user_model.objects.get_or_create(username=username)
                if created:
                    user.set_password(password)
                    user.save(update_fields=["password"])

                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "role": role,
                        "department": (
                            departments[department_code]
                            if department_code is not None
                            else None
                        ),
                    },
                )
                users[username] = user

            for document_id, title, content, owner_name, department_code in DOCUMENTS:
                Document.objects.get_or_create(
                    id=document_id,
                    defaults={
                        "title": title,
                        "content": content,
                        "owner": users[owner_name],
                        "department": departments[department_code],
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Đã chuẩn bị dữ liệu demo: 2 phòng ban, 5 tài khoản, 3 tài liệu. "
                "Mật khẩu của tài khoản đã tồn tại được giữ nguyên."
            )
        )
