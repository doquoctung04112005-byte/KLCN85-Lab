from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import DocumentShare


class DocumentShareForm(forms.ModelForm):
    expires_at = forms.DateTimeField(
        label="Có hiệu lực đến",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "form-control"},
        ),
    )

    class Meta:
        model = DocumentShare
        fields = ("recipient", "permission", "expires_at")
        labels = {
            "recipient": "Tài khoản nhận",
            "permission": "Quyền được cấp",
        }
        widgets = {
            "recipient": forms.Select(attrs={"class": "form-select"}),
            "permission": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, document, **kwargs):
        self.document = document
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = get_user_model().objects.filter(
            profile__department_id=document.department_id
        ).order_by("username")

    def clean_expires_at(self):
        expires_at = self.cleaned_data["expires_at"]
        if expires_at <= timezone.now():
            raise forms.ValidationError("Thời hạn chia sẻ phải ở trong tương lai.")
        return expires_at
