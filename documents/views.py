from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import DocumentForm
from .policies import (
    can_create_document,
    can_delete_document,
    can_edit_document,
    get_user_profile,
    visible_documents,
)


def _access_denied(request, message):
    return render(
        request,
        "documents/access_denied.html",
        {"message": message},
        status=403,
    )


@login_required
@require_GET
def document_list(request):
    profile = get_user_profile(request.user)
    documents = visible_documents(request.user, profile).select_related(
        "owner", "department"
    )
    return render(
        request,
        "documents/list.html",
        {
            "documents": documents,
            "profile": profile,
            "can_create": can_create_document(request.user, profile),
        },
    )


@login_required
@require_GET
def document_detail(request, pk):
    profile = get_user_profile(request.user)
    document = get_object_or_404(
        visible_documents(request.user, profile).select_related("owner", "department"),
        pk=pk,
    )
    return render(
        request,
        "documents/detail.html",
        {
            "document": document,
            "can_edit": can_edit_document(request.user, profile, document),
            "can_delete": can_delete_document(request.user, profile),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def document_create(request):
    profile = get_user_profile(request.user)
    if profile is None:
        return _access_denied(
            request,
            "Tài khoản chưa có hồ sơ. Quản trị viên cần bổ sung hồ sơ trước khi tạo tài liệu.",
        )
    if not can_create_document(request.user, profile):
        return _access_denied(
            request,
            "Hồ sơ chưa có phòng ban. Quản trị viên cần gán phòng ban trước khi tạo tài liệu.",
        )

    form = DocumentForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.owner = request.user
        document.department = profile.department
        document.save()
        return redirect("document_detail", pk=document.pk)

    return render(request, "documents/form.html", {"form": form, "is_edit": False})


@login_required
@require_http_methods(["GET", "POST"])
def document_edit(request, pk):
    profile = get_user_profile(request.user)
    document = get_object_or_404(
        visible_documents(request.user, profile),
        pk=pk,
    )
    if not can_edit_document(request.user, profile, document):
        return _access_denied(request, "Bạn không có quyền sửa tài liệu này.")

    form = DocumentForm(request.POST if request.method == "POST" else None, instance=document)
    if request.method == "POST" and form.is_valid():
        updated_document = form.save(commit=False)
        updated_document.save(update_fields=["title", "content", "updated_at"])
        return redirect("document_detail", pk=document.pk)

    return render(
        request,
        "documents/form.html",
        {"form": form, "document": document, "is_edit": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def document_delete(request, pk):
    profile = get_user_profile(request.user)
    if not can_delete_document(request.user, profile):
        return _access_denied(request, "Bạn không có quyền xóa tài liệu này.")

    document = get_object_or_404(
        visible_documents(request.user, profile).select_related("owner", "department"),
        pk=pk,
    )
    if request.method == "POST":
        document.delete()
        return redirect("document_list")

    return render(
        request,
        "documents/confirm_delete.html",
        {"document": document},
    )
