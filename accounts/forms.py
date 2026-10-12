from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q

from documents.models import Document
from sharing.models import DocumentShare

from .models import Department, UserProfile


PRIVILEGE_FIELDS = {"is_staff", "is_superuser", "groups", "user_permissions"}


def _reject_privilege_fields(form):
    submitted = PRIVILEGE_FIELDS.intersection(form.data.keys())
    if submitted:
        raise ValidationError(
            "Không chấp nhận các trường quyền Django trong biểu mẫu quản lý tài khoản."
        )


class ManagedAccountCreateForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Vai trò ứng dụng",
        choices=UserProfile.Role.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    department = forms.ModelChoiceField(
        label="Phòng ban",
        queryset=Department.objects.order_by("name"),
        required=False,
        empty_label="Chưa gán phòng ban",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "username"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Tên đăng nhập"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "username"}
        )
        self.fields["password1"].label = "Mật khẩu"
        self.fields["password1"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )
        self.fields["password2"].label = "Nhập lại mật khẩu"
        self.fields["password2"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )

    def clean(self):
        _reject_privilege_fields(self)
        return super().clean()


class ManagedAccountUpdateForm(forms.Form):
    role = forms.ChoiceField(
        label="Vai trò ứng dụng",
        choices=UserProfile.Role.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    department = forms.ModelChoiceField(
        label="Phòng ban",
        queryset=Department.objects.order_by("name"),
        required=False,
        empty_label="Chưa gán phòng ban",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    is_active = forms.TypedChoiceField(
        label="Trạng thái tài khoản",
        choices=(("true", "Hoạt động"), ("false", "Bị khóa")),
        coerce=lambda value: value == "true",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(
        self,
        *args,
        target_user,
        actor,
        profile=None,
        active_admin_count,
        lab_self_edit=False,
        **kwargs,
    ):
        self.target_user = target_user
        self.actor = actor
        self.profile = profile
        self.active_admin_count = active_admin_count
        initial = kwargs.pop("initial", {})
        initial.setdefault(
            "role", profile.role if profile else UserProfile.Role.EMPLOYEE
        )
        initial.setdefault("department", profile.department if profile else None)
        initial.setdefault("is_active", "true" if target_user.is_active else "false")
        super().__init__(*args, initial=initial, **kwargs)
        if lab_self_edit:
            # Keep the lab flaw confined to self-assignment of the app role.
            self.fields["department"].disabled = True
            self.fields["is_active"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        _reject_privilege_fields(self)
        if not all(name in cleaned_data for name in ("role", "department", "is_active")):
            return cleaned_data

        role = cleaned_data["role"]
        department = cleaned_data["department"]
        is_active = cleaned_data["is_active"]
        department_id = department.pk if department else None
        old_department_id = self.profile.department_id if self.profile else None

        if self.target_user.pk == self.actor.pk and not is_active:
            self.add_error("is_active", "Bạn không thể khóa tài khoản đang sử dụng.")

        is_active_app_admin = bool(
            self.profile
            and self.profile.role == UserProfile.Role.ADMIN
            and self.target_user.is_active
        )
        will_remain_active_admin = role == UserProfile.Role.ADMIN and is_active
        if (
            is_active_app_admin
            and not will_remain_active_admin
            and self.active_admin_count <= 1
        ):
            self.add_error(
                "role",
                "Không thể thay đổi tài khoản này vì đây là quản trị viên ứng dụng đang hoạt động cuối cùng.",
            )

        if department_id != old_department_id:
            documents_in_other_departments = Document.objects.filter(
                owner=self.target_user
            ).exclude(department_id=department_id)
            document_count = documents_in_other_departments.count()

            related_shares = DocumentShare.objects.filter(
                Q(recipient=self.target_user) | Q(granted_by=self.target_user)
            ).exclude(document__department_id=department_id)
            share_count = related_shares.count()

            if document_count:
                self.add_error(
                    "department",
                    f"Không thể chuyển phòng ban: tài khoản đang sở hữu {document_count} tài liệu thuộc phòng ban khác. Hãy xử lý các tài liệu đó trước.",
                )
            if share_count:
                self.add_error(
                    "department",
                    f"Không thể chuyển phòng ban: tài khoản đang liên quan đến {share_count} lượt chia sẻ gắn với tài liệu ở phòng ban khác.",
                )

        return cleaned_data


def account_changes(*, user, profile, cleaned_data):
    old_role = profile.role if profile else None
    old_department_id = profile.department_id if profile else None
    department = cleaned_data["department"]
    new_department_id = department.pk if department else None
    changes = []
    if old_role != cleaned_data["role"]:
        changes.append("role")
    if old_department_id != new_department_id:
        changes.append("department")
    if user.is_active != cleaned_data["is_active"]:
        changes.append("is_active")
    return changes
