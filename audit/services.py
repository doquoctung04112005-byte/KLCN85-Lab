import json
import logging
from logging.handlers import RotatingFileHandler

from django.conf import settings
from django.utils import timezone

from .models import AuditLog


class _AuditJsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(record.audit_event, ensure_ascii=False, separators=(",", ":"))


def _event_logger():
    logger = logging.getLogger("audit.events")
    if not getattr(logger, "_audit_handler_configured", False):
        log_path = settings.AUDIT_LOG_FILE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(_AuditJsonFormatter())
        logger.addHandler(handler)
        logger._audit_file_handler = handler
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger._audit_handler_configured = True
    return logger


def record_event(
    *, actor, action, object_type, object_id, result, changed_fields=()
):
    """Persist one safe audit event in PostgreSQL and in the local JSONL file."""
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    safe_changed_fields = [
        field
        for field in changed_fields
        if field in {"role", "department", "is_active"}
    ]
    event = AuditLog.objects.create(
        actor=actor,
        action=str(action)[:100],
        object_type=str(object_type)[:100],
        object_id=str(object_id)[:255],
        result=str(result)[:50],
        details={"changed_fields": safe_changed_fields} if safe_changed_fields else {},
    )
    actor_name = event.actor.get_username() if event.actor_id else None
    payload = {
        "timestamp": timezone.localtime(event.created_at).isoformat(),
        "actor_id": event.actor_id,
        "actor_username": actor_name,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "result": event.result,
    }
    _event_logger().info("audit_event", extra={"audit_event": payload})
    return event
