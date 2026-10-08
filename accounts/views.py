from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from documents.policies import get_user_profile, is_admin_profile


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
    profile = get_user_profile(request.user)
    if not is_admin_profile(request.user, profile):
        return render(
            request,
            "accounts/access_denied.html",
            {"message": "Bạn không có quyền xem danh sách người dùng."},
            status=403,
        )

    users = []
    for user in get_user_model().objects.select_related("profile__department").order_by("username"):
        user_profile = getattr(user, "profile", None)
        users.append(
            {
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
