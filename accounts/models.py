from django.conf import settings
from django.db import models


class Department(models.Model):
    code = models.CharField("Mã phòng ban", max_length=20, unique=True)
    name = models.CharField("Tên phòng ban", max_length=150)
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "phòng ban"
        verbose_name_plural = "phòng ban"

    def __str__(self):
        return f"{self.code} - {self.name}"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Nhân viên"
        DEPARTMENT_HEAD = "department_head", "Trưởng phòng"
        ADMIN = "admin", "Quản trị viên"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Tài khoản",
    )
    role = models.CharField(
        "Vai trò",
        max_length=32,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name="user_profiles",
        null=True,
        blank=True,
        verbose_name="Phòng ban",
    )

    class Meta:
        verbose_name = "hồ sơ người dùng"
        verbose_name_plural = "hồ sơ người dùng"

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"
