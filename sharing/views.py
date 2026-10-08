from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from documents.models import Document
from documents.policies import (
    can_manage_document_shares,
    can_revoke_document_share,
    get_user_profile,
    is_admin_profile,
)

from .forms import DocumentShareForm
from .models import DocumentShare


def _access_denied(request):
    return render(
        request,
        "documents/access_denied.html",
        {"message": "Bạn không có quyền quản lý lượt chia sẻ này."},
        status=403,
    )


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def manage_document_shares(request, document_pk):
    document = get_object_or_404(
        Document.objects.select_related("owner", "department"),
        pk=document_pk,
    )
    profile = get_user_profile(request.user)
    if not can_manage_document_shares(request.user, profile, document):
        return _access_denied(request)

    if request.method == "POST":
        form = DocumentShareForm(request.POST, document=document)
        if form.is_valid():
            share = form.save(commit=False)
            share.document = document
            share.granted_by = request.user
            share.save()
            messages.success(request, "Đã cấp quyền chia sẻ tài liệu.")
            return redirect("document_share_manage", document_pk=document.pk)
    else:
        form = DocumentShareForm(document=document)

    shares = DocumentShare.objects.filter(document=document).select_related(
        "recipient", "granted_by"
    )
    if not is_admin_profile(request.user, profile):
        shares = shares.filter(granted_by=request.user)

    return render(
        request,
        "sharing/manage.html",
        {
            "document": document,
            "form": form,
            "shares": shares,
            "now": timezone.now(),
        },
    )


@login_required
@csrf_protect
@require_POST
def revoke_document_share(request, share_pk):
    share = get_object_or_404(
        DocumentShare.objects.select_related("document"),
        pk=share_pk,
    )
    profile = get_user_profile(request.user)
    if not can_revoke_document_share(request.user, profile, share):
        return _access_denied(request)

    if share.revoked_at is None:
        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at"])
        messages.success(request, "Đã thu hồi lượt chia sẻ.")

    return redirect("document_share_manage", document_pk=share.document_id)
