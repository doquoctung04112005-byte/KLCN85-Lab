from django.db.models import F
from django.utils import timezone

from accounts.models import UserProfile
from sharing.models import DocumentShare

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


def active_document_shares(user, document=None, permission=None):
    if not user.is_authenticated:
        return DocumentShare.objects.none()

    shares = DocumentShare.objects.filter(
        recipient_id=user.pk,
        recipient__profile__department_id=F("document__department_id"),
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if document is not None:
        shares = shares.filter(document_id=document.pk)
    if permission is not None:
        shares = shares.filter(permission=permission)
    return shares


def has_active_document_shares(document):
    return DocumentShare.objects.filter(
        document=document,
        recipient__profile__department_id=F("document__department_id"),
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).exists()


def visible_documents(user, profile):
    if not _profile_belongs_to(user, profile):
        return Document.objects.none()

    if is_admin_profile(user, profile):
        return Document.objects.all()

    shared_documents = Document.objects.filter(
        pk__in=active_document_shares(user).values("document_id")
    )

    if profile.role == UserProfile.Role.DEPARTMENT_HEAD:
        base_documents = (
            Document.objects.filter(department_id=profile.department_id)
            if profile.department_id is not None
            else Document.objects.none()
        )
    elif profile.role == UserProfile.Role.EMPLOYEE:
        base_documents = Document.objects.filter(owner_id=user.pk)
    else:
        base_documents = Document.objects.none()

    return (base_documents | shared_documents).distinct()


def can_view_document(user, profile, document):
    return visible_documents(user, profile).filter(pk=document.pk).exists()


def can_edit_document(user, profile, document):
    if not can_view_document(user, profile, document):
        return False
    return (
        is_admin_profile(user, profile)
        or document.owner_id == user.pk
        or active_document_shares(
            user,
            document=document,
            permission=DocumentShare.Permission.EDIT,
        ).exists()
    )


def can_delete_document(user, profile):
    return is_admin_profile(user, profile)


def can_create_document(user, profile):
    return _profile_belongs_to(user, profile) and profile.department_id is not None


def can_manage_document_shares(user, profile, document):
    return is_admin_profile(user, profile) or (
        _profile_belongs_to(user, profile) and document.owner_id == user.pk
    )


def can_revoke_document_share(user, profile, share):
    return is_admin_profile(user, profile) or (
        _profile_belongs_to(user, profile) and share.granted_by_id == user.pk
    )
