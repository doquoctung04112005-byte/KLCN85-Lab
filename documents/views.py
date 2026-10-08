from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods

from .forms import DocumentForm
from .models import Document, DocumentAttachment, DocumentFolder
from .policies import (
    active_document_shares,
    can_create_document,
    can_delete_document,
    can_edit_document,
    can_manage_document_shares,
    can_view_document,
    get_user_profile,
    has_active_document_shares,
    is_admin_profile,
    visible_documents,
)
from .previews import office_preview
from .services import save_document_attachment
from accounts.models import UserProfile
from sharing.models import DocumentShare


FILE_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def _filter_documents(queryset, request):
    query = request.GET.get("q", "").strip()[:100]
    file_type = request.GET.get("type", "")
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(attachment__display_name__icontains=query)
        )
    if file_type == "text":
        queryset = queryset.filter(attachment__isnull=True)
    elif file_type in FILE_CONTENT_TYPES:
        queryset = queryset.filter(attachment__file_type=file_type)

    sort = request.GET.get("sort", "recent")
    queryset = queryset.order_by("updated_at" if sort == "oldest" else "-updated_at")
    active_shares = DocumentShare.objects.filter(
        document_id=OuterRef("pk"),
        recipient__profile__department_id=OuterRef("department_id"),
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    queryset = queryset.annotate(has_active_shares=Exists(active_shares))
    return queryset, query, file_type, sort


def _prepare_document_rows(documents, user, profile):
    rows = list(documents)
    can_delete = can_delete_document(user, profile)
    for document in rows:
        document.ui_can_edit = can_edit_document(user, profile, document)
        document.ui_can_manage_shares = can_manage_document_shares(
            user, profile, document
        )
        document.ui_can_delete = can_delete
    return rows


def _document_scopes(user, profile):
    if is_admin_profile(user, profile):
        return "all", (
            ("all", "Toàn hệ thống"),
            ("mine", "Tài liệu của tôi"),
            ("shared", "Được chia sẻ với tôi"),
        )
    if profile and profile.role == UserProfile.Role.DEPARTMENT_HEAD:
        return "all", (
            ("all", "Tài liệu được phép xem"),
            ("department", "Tài liệu trong phòng"),
            ("mine", "Tài liệu của tôi"),
            ("shared", "Được chia sẻ với tôi"),
        )
    return "all", (
        ("all", "Tài liệu được phép xem"),
        ("mine", "Tài liệu của tôi"),
        ("shared", "Được chia sẻ với tôi"),
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
    allowed_documents = visible_documents(request.user, profile)
    default_scope, scope_options = _document_scopes(request.user, profile)
    scope = request.GET.get("scope", default_scope)
    allowed_scopes = {option[0] for option in scope_options}
    if scope not in allowed_scopes:
        scope = default_scope

    if scope == "mine":
        documents = allowed_documents.filter(owner=request.user)
    elif scope == "shared":
        documents = allowed_documents.filter(
            pk__in=active_document_shares(request.user).values("document_id")
        )
    elif scope == "department" and profile and profile.department_id:
        documents = allowed_documents.filter(department_id=profile.department_id)
    else:
        documents = allowed_documents

    documents, query, file_type, sort = _filter_documents(documents, request)
    documents = documents.select_related(
        "owner", "department", "folder", "attachment"
    )
    documents = _prepare_document_rows(documents, request.user, profile)
    if scope == "shared":
        root_folders = DocumentFolder.objects.none()
    elif is_admin_profile(request.user, profile):
        root_folders = DocumentFolder.objects.filter(parent__isnull=True)
        if scope == "mine":
            root_folders = root_folders.filter(owner=request.user)
    elif profile and profile.role == UserProfile.Role.DEPARTMENT_HEAD:
        root_folders = DocumentFolder.objects.filter(
            department_id=profile.department_id, parent__isnull=True
        )
    else:
        root_folders = DocumentFolder.objects.filter(
            owner=request.user, parent__isnull=True
        )
    return render(
        request,
        "documents/list.html",
        {
            "documents": documents,
            "root_folders": root_folders,
            "profile": profile,
            "can_create": can_create_document(request.user, profile),
            "scope": scope,
            "scope_options": scope_options,
            "query": query,
            "file_type": file_type,
            "sort": sort,
        },
    )


@login_required
@require_GET
def document_detail(request, pk):
    profile = get_user_profile(request.user)
    document = get_object_or_404(
        visible_documents(request.user, profile).select_related(
            "owner", "department", "folder", "attachment"
        ),
        pk=pk,
    )
    try:
        attachment = document.attachment
    except DocumentAttachment.DoesNotExist:
        attachment = None
    can_manage_shares = can_manage_document_shares(request.user, profile, document)
    if can_manage_shares:
        shares = DocumentShare.objects.filter(document=document).select_related(
            "recipient", "granted_by"
        )
    else:
        shares = DocumentShare.objects.filter(
            document=document,
            recipient=request.user,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related("recipient", "granted_by")
    return render(
        request,
        "documents/detail.html",
        {
            "document": document,
            "attachment": attachment,
            "can_edit": can_edit_document(request.user, profile, document),
            "can_delete": can_delete_document(request.user, profile),
            "can_manage_shares": can_manage_document_shares(
                request.user, profile, document
            ),
            "shares": shares,
            "share_records_visible": can_manage_shares,
            "now": timezone.now(),
            "metadata": {
                "owner": document.owner,
                "file_type": attachment.file_type if attachment else "text",
                "file_size": attachment.file_size if attachment else 0,
                "created_at": attachment.created_at if attachment else document.created_at,
                "updated_at": attachment.updated_at if attachment else document.updated_at,
                "sharing_status": (
                    "shared_with_you"
                    if active_document_shares(request.user, document=document).exists()
                    else "shared"
                    if has_active_document_shares(document)
                    else "private"
                ),
            },
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

    form = DocumentForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        user=request.user,
        profile=profile,
    )
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.owner = request.user
        document.department = profile.department
        document.save()
        if form.cleaned_data.get("upload"):
            save_document_attachment(document, form.cleaned_data["upload"])
        messages.success(request, "Tài liệu đã được tạo.")
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

    form = DocumentForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        instance=document,
        user=request.user,
        profile=profile,
    )
    if request.method == "POST" and form.is_valid():
        updated_document = form.save(commit=False)
        update_fields = ["title", "content", "updated_at"]
        if "folder" in form.fields:
            update_fields.append("folder")
        updated_document.save(update_fields=update_fields)
        if form.cleaned_data.get("upload"):
            save_document_attachment(updated_document, form.cleaned_data["upload"])
        messages.success(request, "Thay đổi đã được lưu.")
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
        messages.success(request, "Tài liệu đã được xóa.")
        return redirect("document_list")

    return render(
        request,
        "documents/confirm_delete.html",
        {"document": document},
    )


def _get_viewable_document(request, pk):
    profile = get_user_profile(request.user)
    document = get_object_or_404(
        Document.objects.select_related("owner", "department"),
        pk=pk,
    )
    if not can_view_document(request.user, profile, document):
        raise Http404
    return document


def _file_response(attachment, *, as_attachment, content_type):
    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=as_attachment,
        filename=attachment.display_name,
        content_type=content_type,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def document_download(request, pk):
    document = _get_viewable_document(request, pk)
    attachment = get_object_or_404(DocumentAttachment, document=document)
    return _file_response(
        attachment,
        as_attachment=True,
        content_type=FILE_CONTENT_TYPES[attachment.file_type],
    )


@login_required
@require_GET
@xframe_options_sameorigin
def document_preview(request, pk):
    document = _get_viewable_document(request, pk)
    attachment = get_object_or_404(DocumentAttachment, document=document)
    if attachment.file_type in {"docx", "xlsx"}:
        with attachment.file.open("rb") as office_file:
            preview_type, preview_data = office_preview(attachment.file_type, office_file)
        return render(
            request,
            "documents/office_preview.html",
            {
                "document": document,
                "attachment": attachment,
                "preview_type": preview_type,
                "preview_data": preview_data,
            },
        )
    if attachment.file_type not in {"pdf", "png", "jpg", "jpeg"}:
        raise Http404("Tệp này không hỗ trợ xem trước.")
    return _file_response(
        attachment,
        as_attachment=False,
        content_type=FILE_CONTENT_TYPES[attachment.file_type],
    )
