import uuid

from django.conf import settings
from django.db import models

from accounts.models import Department


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField("Tiêu đề", max_length=255)
    content = models.TextField("Nội dung")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_documents",
        verbose_name="Người sở hữu",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name="Phòng ban",
    )
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("Ngày cập nhật", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "tài liệu"
        verbose_name_plural = "tài liệu"

    def __str__(self):
        return self.title
