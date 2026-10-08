from accounts.models import UserProfile

from .models import Document


def get_user_profile(user):
    if not user.is_authenticated:
        return None
    return UserProfile.objects.select_related("department").filter(user=user).first()


def _profile_belongs_to(user, profile):
    return bool(
        user.is_authenticated
        and profile is not None
        and profile.user_id == user.pk
    )


def is_admin_profile(user, profile):
    return _profile_belongs_to(user, profile) and profile.role == UserProfile.Role.ADMIN


def visible_documents(user, profile):
    if not _profile_belongs_to(user, profile):
        return Document.objects.none()

    if is_admin_profile(user, profile):
        return Document.objects.all()

    if profile.role == UserProfile.Role.DEPARTMENT_HEAD:
        if profile.department_id is None:
            return Document.objects.none()
        return Document.objects.filter(department_id=profile.department_id)

    if profile.role == UserProfile.Role.EMPLOYEE:
        return Document.objects.filter(owner_id=user.pk)

    return Document.objects.none()


def can_view_document(user, profile, document):
    return visible_documents(user, profile).filter(pk=document.pk).exists()


def can_edit_document(user, profile, document):
    return can_view_document(user, profile, document) and (
        is_admin_profile(user, profile) or document.owner_id == user.pk
    )


def can_delete_document(user, profile):
    return is_admin_profile(user, profile)


def can_create_document(user, profile):
    return _profile_belongs_to(user, profile) and profile.department_id is not None
