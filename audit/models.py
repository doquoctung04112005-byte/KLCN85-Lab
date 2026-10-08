from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
        verbose_name="Người thực hiện",
    )
    action = models.CharField("Tên thao tác", max_length=100)
    object_type = models.CharField("Loại đối tượng", max_length=100)
    object_id = models.CharField("Mã đối tượng", max_length=255)
    result = models.CharField("Kết quả", max_length=50)
    details = models.JSONField("Thông tin chi tiết", default=dict, blank=True)
    created_at = models.DateTimeField("Thời gian tạo", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "nhật ký kiểm toán"
        verbose_name_plural = "nhật ký kiểm toán"

    def __str__(self):
        return f"{self.action} - {self.object_type}:{self.object_id} ({self.result})"
