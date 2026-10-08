from django import forms
from django.core.exceptions import ValidationError

from .models import Document, DocumentAttachment, DocumentFolder
from .validators import validate_document_upload


class DocumentForm(forms.ModelForm):
    upload = forms.FileField(
        label="Tệp đính kèm",
        required=False,
        validators=[validate_document_upload],
        help_text="PDF, DOCX, XLSX, PNG hoặc JPG/JPEG; tối đa 20 MB.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "sr-only",
                "accept": ".pdf,.docx,.xlsx,.png,.jpg,.jpeg",
                "data-file-picker": "true",
            }
        ),
    )

    class Meta:
        model = Document
        fields = ("title", "content", "folder")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 10}),
            "folder": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user, profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile
        document = self.instance
        is_new = document._state.adding
        can_move = (
            is_new
            or document.owner_id == user.pk
            or bool(profile and profile.role == "admin")
        )
        if not can_move:
            self.fields.pop("folder")
            return

        if not is_new:
            owner_id = document.owner_id
            department_id = document.department_id
        else:
            owner_id = user.pk
            department_id = profile.department_id if profile else None
        self.fields["folder"].queryset = DocumentFolder.objects.filter(
            owner_id=owner_id,
            department_id=department_id,
        ).order_by("name")

    def clean_folder(self):
        folder = self.cleaned_data.get("folder")
        if folder is None:
            return None

        document = self.instance
        is_new = document._state.adding
        owner_id = document.owner_id if not is_new else self.user.pk
        department_id = (
            document.department_id
            if not is_new
            else self.profile.department_id if self.profile else None
        )
        if folder.owner_id != owner_id or folder.department_id != department_id:
            raise ValidationError("Thư mục phải cùng chủ sở hữu và phòng ban với tài liệu.")
        return folder

    def clean(self):
        cleaned_data = super().clean()
        content = (cleaned_data.get("content") or "").strip()
        upload = cleaned_data.get("upload")
        has_existing_attachment = False
        if not self.instance._state.adding:
            has_existing_attachment = DocumentAttachment.objects.filter(
                document=self.instance
            ).exists()
        if not content and not upload and not has_existing_attachment:
            self.add_error("content", "Nhập nội dung hoặc đính kèm một tệp.")
        return cleaned_data
