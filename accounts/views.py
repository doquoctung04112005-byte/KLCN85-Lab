from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from audit.services import record_event
from documents.policies import get_user_profile, is_admin_profile

from .forms import (
    ManagedAccountCreateForm,
    ManagedAccountUpdateForm,
    account_changes,
)
from .models import UserProfile


@login_required
def dashboard(request):
    return render(
        request,
        "accounts/dashboard.html",
        {"profile": get_user_profile(request.user)},
    )


@login_required
def profile(request):
    return render(
        request,
        "accounts/profile.html",
        {"profile": get_user_profile(request.user)},
    )


@login_required
@require_GET
def user_list(request):
    # Intentional OWASP A01 forced browsing: login is checked, but the admin
    # role is not checked before returning the real account directory.
    users = []
    for user in get_user_model().objects.select_related("profile__department").order_by("username"):
        user_profile = getattr(user, "profile", None)
        users.append(
            {
                "id": user.pk,
                "username": user.get_username(),
                "role": user_profile.get_role_display() if user_profile else "Chưa có hồ sơ",
                "department": (
                    user_profile.department.name
                    if user_profile and user_profile.department
                    else "Chưa có phòng ban"
                ),
                "is_active": user.is_active,
            }
        )

    return render(request, "accounts/user_list.html", {"users": users})


def _account_admin_denied(request, action, object_id):
    record_event(
        actor=request.user,
        action=action,
        object_type="account",
        object_id=object_id,
        result="denied",
    )
    return render(
        request,
        "accounts/access_denied.html",
        {"message": "Chỉ quản trị viên ứng dụng được phép quản lý tài khoản."},
        status=403,
    )


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def user_create(request):
    profile = get_user_profile(request.user)
    if not is_admin_profile(request.user, profile):
        return _account_admin_denied(request, "account.create", "new")

    form = ManagedAccountCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                UserProfile.objects.create(
                    user=user,
                    role=form.cleaned_data["role"],
                    department=form.cleaned_data["department"],
                )
        except IntegrityError:
            form.add_error("username", "Tên đăng nhập này đã được sử dụng.")
        else:
            record_event(
                actor=request.user,
                action="account.create",
                object_type="account",
                object_id=user.pk,
                result="success",
            )
            messages.success(request, "Tài khoản đã được tạo.")
            return redirect("user_list")

    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "mode": "create"},
    )


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def user_edit(request, user_pk):
    profile = get_user_profile(request.user)
    is_app_admin = is_admin_profile(request.user, profile)
    # Intentional vertical privilege escalation in the local coursework lab:
    # employees may edit their own account, including its application role.
    lab_self_edit = (
        not is_app_admin
        and profile is not None
        and profile.role == UserProfile.Role.EMPLOYEE
        and request.user.pk == user_pk
    )
    if not is_app_admin and not lab_self_edit:
        return _account_admin_denied(request, "account.update", user_pk)

    user_model = get_user_model()
    target_user = get_object_or_404(user_model, pk=user_pk)
    target_profile = UserProfile.objects.filter(user=target_user).select_related(
        "department"
    ).first()
    saved_changes = None
    cleaned_data = None
    form_is_valid = False

    if request.method == "POST":
        with transaction.atomic():
            active_admin_ids = list(
                user_model.objects.select_for_update()
                .filter(is_active=True, profile__role=UserProfile.Role.ADMIN)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            target_user = get_object_or_404(
                user_model.objects.select_for_update(), pk=user_pk
            )
            target_profile = UserProfile.objects.filter(user=target_user).first()
            form = ManagedAccountUpdateForm(
                request.POST,
                target_user=target_user,
                actor=request.user,
                profile=target_profile,
                active_admin_count=len(active_admin_ids),
                lab_self_edit=lab_self_edit,
            )
            form_is_valid = form.is_valid()
            if form_is_valid:
                saved_changes = account_changes(
                    user=target_user,
                    profile=target_profile,
                    cleaned_data=form.cleaned_data,
                )
                cleaned_data = form.cleaned_data
                if saved_changes:
                    if target_profile is None:
                        target_profile = UserProfile(user=target_user)
                    target_profile.role = form.cleaned_data["role"]
                    target_profile.department = form.cleaned_data["department"]
                    target_profile.save()

                    target_user.is_active = form.cleaned_data["is_active"]
                    target_user.save(update_fields=["is_active"])
    else:
        active_admin_count = user_model.objects.filter(
            is_active=True,
            profile__role=UserProfile.Role.ADMIN,
        ).count()
        form = ManagedAccountUpdateForm(
            target_user=target_user,
            actor=request.user,
            profile=target_profile,
            active_admin_count=active_admin_count,
            lab_self_edit=lab_self_edit,
        )

    if request.method == "POST" and form_is_valid:
        if saved_changes:
            if "is_active" in saved_changes:
                action = (
                    "account.unlock" if cleaned_data["is_active"] else "account.lock"
                )
            else:
                action = "account.update"
            record_event(
                actor=request.user,
                action=action,
                object_type="account",
                object_id=target_user.pk,
                result="success",
                changed_fields=saved_changes,
            )
            messages.success(request, "Thông tin tài khoản đã được cập nhật.")
        else:
            messages.info(request, "Không có thay đổi cần lưu.")
        return redirect("profile" if lab_self_edit else "user_list")

    return render(
        request,
        "accounts/user_form.html",
        {
            "form": form,
            "mode": "edit",
            "target_user": target_user,
            "lab_self_edit": lab_self_edit,
        },
    )
