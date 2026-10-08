import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import Department
from .storage import PrivateDocumentStorage


class DocumentFolder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("Tên thư mục", max_length=150)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="document_folders",
        verbose_name="Chủ sở hữu",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="document_folders",
        verbose_name="Phòng ban",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="Thư mục cha",
    )
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("Ngày cập nhật", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "thư mục tài liệu"
        verbose_name_plural = "thư mục tài liệu"

    def clean(self):
        super().clean()
        if self.parent_id and (
            self.parent.owner_id != self.owner_id
            or self.parent.department_id != self.department_id
        ):
            raise ValidationError({"parent": "Thư mục cha phải cùng chủ sở hữu và phòng ban."})

        ancestor = self.parent
        visited = set()
        while ancestor is not None:
            if ancestor.pk == self.pk or ancestor.pk in visited:
                raise ValidationError({"parent": "Không thể chuyển thư mục vào chính nó hoặc thư mục con."})
            visited.add(ancestor.pk)
            ancestor = ancestor.parent

    def __str__(self):
        return self.name


def document_file_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return f"{uuid.uuid4().hex}.{extension}"


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField("Tiêu đề", max_length=255)
    content = models.TextField("Nội dung", blank=True)
    folder = models.ForeignKey(
        DocumentFolder,
        on_delete=models.SET_NULL,
        related_name="documents",
        null=True,
        blank=True,
        verbose_name="Thư mục",
    )
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


class DocumentAttachment(models.Model):
    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"
        XLSX = "xlsx", "XLSX"
        PNG = "png", "PNG"
        JPG = "jpg", "JPG"
        JPEG = "jpeg", "JPEG"

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="attachment",
        verbose_name="Tài liệu",
    )
    file = models.FileField(
        "Tệp lưu trữ",
        upload_to=document_file_upload_to,
        storage=PrivateDocumentStorage(),
        max_length=255,
    )
    display_name = models.CharField("Tên hiển thị", max_length=255)
    file_type = models.CharField("Loại tệp", max_length=4, choices=FileType.choices)
    file_size = models.PositiveBigIntegerField("Dung lượng (byte)")
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("Ngày cập nhật", auto_now=True)

    class Meta:
        ordering = ["display_name"]
        verbose_name = "tệp đính kèm"
        verbose_name_plural = "tệp đính kèm"

    def __str__(self):
        return self.display_name
