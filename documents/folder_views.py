from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from accounts.models import UserProfile

from .folder_forms import DocumentFolderForm
from .models import DocumentFolder
from .policies import get_user_profile, is_admin_profile, visible_documents
from .views import _filter_documents, _prepare_document_rows


def _can_manage_folder(user, profile, folder):
    return is_admin_profile(user, profile) or (
        profile is not None
        and profile.user_id == user.pk
        and folder.owner_id == user.pk
    )


def _visible_folders(user, profile):
    if is_admin_profile(user, profile):
        return DocumentFolder.objects.all()
    if profile and profile.user_id == user.pk:
        if profile.role == UserProfile.Role.DEPARTMENT_HEAD and profile.department_id:
            return DocumentFolder.objects.filter(department_id=profile.department_id)
        return DocumentFolder.objects.filter(owner=user)
    return DocumentFolder.objects.none()


@login_required
@require_GET
def folder_list(request):
    profile = get_user_profile(request.user)
    folders = _visible_folders(request.user, profile).filter(parent__isnull=True)
    return render(
        request,
        "documents/folder_list.html",
        {
            "folders": folders,
            "can_create": bool(profile and profile.department_id),
            "is_admin": is_admin_profile(request.user, profile),
        },
    )


@login_required
@require_GET
def folder_detail(request, folder_pk):
    profile = get_user_profile(request.user)
    folder = get_object_or_404(_visible_folders(request.user, profile), pk=folder_pk)
    children = DocumentFolder.objects.filter(
        parent=folder,
        owner_id=folder.owner_id,
        department_id=folder.department_id,
    )
    documents = visible_documents(request.user, profile).filter(folder=folder)
    documents, query, file_type, sort = _filter_documents(documents, request)
    documents = documents.select_related("owner", "department", "attachment")
    documents = _prepare_document_rows(documents, request.user, profile)

    ancestors = []
    parent = folder.parent
    while parent is not None:
        ancestors.append(parent)
        parent = parent.parent
    ancestors.reverse()

    return render(
        request,
        "documents/folder_detail.html",
        {
            "folder": folder,
            "children": children,
            "documents": documents,
            "ancestors": ancestors,
            "can_manage": _can_manage_folder(request.user, profile, folder),
            "query": query,
            "file_type": file_type,
            "sort": sort,
        },
    )


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def folder_create(request):
    profile = get_user_profile(request.user)
    if not profile or not profile.department_id:
        return render(
            request,
            "documents/access_denied.html",
            {"message": "Tài khoản cần có phòng ban để tạo thư mục."},
            status=403,
        )

    if request.method == "POST":
        form = DocumentFolderForm(
            request.POST,
            owner=request.user,
            department=profile.department,
        )
        if form.is_valid():
            folder = form.save(commit=False)
            folder.owner = request.user
            folder.department = profile.department
            folder.save()
            messages.success(request, "Thư mục đã được tạo.")
            if folder.parent_id:
                return redirect("folder_detail", folder_pk=folder.parent_id)
            return redirect("folder_list")
    else:
        initial = {}
        parent_id = request.GET.get("parent")
        if parent_id:
            initial["parent"] = get_object_or_404(
                DocumentFolder.objects.filter(
                    owner=request.user,
                    department=profile.department,
                ),
                pk=parent_id,
            )
        form = DocumentFolderForm(
            owner=request.user,
            department=profile.department,
            initial=initial,
        )

    return render(
        request,
        "documents/folder_form.html",
        {"form": form, "heading": "Tạo thư mục"},
    )


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def folder_manage(request, folder_pk):
    profile = get_user_profile(request.user)
    folder = get_object_or_404(
        DocumentFolder.objects.select_related("owner", "department", "parent"),
        pk=folder_pk,
    )
    if not _can_manage_folder(request.user, profile, folder):
        raise Http404

    if request.method == "POST":
        form = DocumentFolderForm(
            request.POST,
            instance=folder,
            owner=folder.owner,
            department=folder.department,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Thư mục đã được cập nhật.")
            return redirect("folder_detail", folder_pk=folder.pk)
    else:
        form = DocumentFolderForm(
            instance=folder,
            owner=folder.owner,
            department=folder.department,
        )

    return render(
        request,
        "documents/folder_form.html",
        {"form": form, "folder": folder, "heading": "Đổi tên hoặc chuyển thư mục"},
    )
