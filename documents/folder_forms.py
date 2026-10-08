from django import forms
from django.core.exceptions import ValidationError

from .models import DocumentFolder


def _descendant_ids(folder):
    descendants = {folder.pk}
    frontier = {folder.pk}
    while frontier:
        children = set(
            DocumentFolder.objects.filter(parent_id__in=frontier).values_list(
                "pk", flat=True
            )
        )
        frontier = children - descendants
        descendants.update(frontier)
    return descendants


class DocumentFolderForm(forms.ModelForm):
    class Meta:
        model = DocumentFolder
        fields = ("name", "parent")
        labels = {"name": "Tên thư mục", "parent": "Thư mục cha"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, owner, department, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.department = department
        folders = DocumentFolder.objects.filter(
            owner=owner,
            department=department,
        )
        if self.instance.pk and not self.instance._state.adding:
            folders = folders.exclude(pk__in=_descendant_ids(self.instance))
        self.fields["parent"].queryset = folders.order_by("name")

    def _post_clean(self):
        # These values are assigned by the view, not accepted from POST. Set
        # them before ModelForm calls the model's cross-field validation.
        self.instance.owner = self.owner
        self.instance.department = self.department
        super()._post_clean()

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent is None:
            return None
        if parent.owner_id != self.owner.pk or parent.department_id != self.department.pk:
            raise ValidationError("Thư mục cha phải cùng chủ sở hữu và phòng ban.")
        if self.instance.pk and not self.instance._state.adding:
            if parent.pk in _descendant_ids(self.instance):
                raise ValidationError("Không thể chuyển thư mục vào chính nó hoặc thư mục con.")
        return parent
