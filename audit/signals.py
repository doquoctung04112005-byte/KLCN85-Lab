from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .services import record_event


@receiver(user_logged_in, dispatch_uid="audit_successful_login")
def audit_successful_login(sender, request, user, **kwargs):
    if request is None:
        return
    record_event(
        actor=user,
        action="login.success",
        object_type="authentication",
        object_id="login",
        result="success",
    )


@receiver(user_login_failed, dispatch_uid="audit_failed_login")
def audit_failed_login(sender, request, **kwargs):
    if request is None:
        return
    # Do not persist any credentials: the signal includes the attempted password.
    record_event(
        actor=None,
        action="login.failure",
        object_type="authentication",
        object_id="login",
        result="denied",
    )
