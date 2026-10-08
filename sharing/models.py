from django.conf import settings
from django.db import models

from documents.models import Document


class DocumentShare(models.Model):
    class Permission(models.TextChoices):
        VIEW = "view", "Xem"
        EDIT = "edit", "Chỉnh sửa"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="shares",
        verbose_name="Tài liệu",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="granted_document_shares",
        verbose_name="Người cấp quyền",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_document_shares",
        verbose_name="Người nhận",
    )
    permission = models.CharField(
        "Loại quyền",
        max_length=10,
        choices=Permission.choices,
    )
    expires_at = models.DateTimeField("Thời hạn", null=True, blank=True)
    created_at = models.DateTimeField("Thời điểm tạo", auto_now_add=True)
    revoked_at = models.DateTimeField("Thời điểm thu hồi", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "lượt chia sẻ tài liệu"
        verbose_name_plural = "lượt chia sẻ tài liệu"

    def __str__(self):
        return f"{self.document} → {self.recipient} ({self.get_permission_display()})"
