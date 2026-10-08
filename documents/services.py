from pathlib import PurePosixPath
import uuid

from django.utils import timezone

from .models import Document, DocumentAttachment
from .validators import document_file_extension


def _display_filename(upload):
    path_name = PurePosixPath(upload.name.replace("\\", "/")).name
    safe_name = "".join(character for character in path_name if character.isprintable())
    return safe_name[:255] or "uploaded-file"


def save_document_attachment(document, upload):
    try:
        attachment = document.attachment
    except DocumentAttachment.DoesNotExist:
        attachment = DocumentAttachment(document=document)

    old_storage = attachment.file.storage if attachment.file else None
    old_name = attachment.file.name if attachment.file else None
    extension = document_file_extension(upload)
    attachment.display_name = _display_filename(upload)
    attachment.file_type = extension.removeprefix(".")
    attachment.file_size = upload.size

    try:
        attachment.file.save(f"{uuid.uuid4().hex}{extension}", upload, save=False)
        attachment.save()
    except Exception:
        if attachment.file.name and attachment.file.name != old_name:
            attachment.file.storage.delete(attachment.file.name)
        raise

    if old_name and old_storage and old_name != attachment.file.name:
        old_storage.delete(old_name)
    document.updated_at = timezone.now()
    Document.objects.filter(pk=document.pk).update(updated_at=document.updated_at)
    return attachment
