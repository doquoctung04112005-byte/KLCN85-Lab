from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError


MAX_DOCUMENT_UPLOAD_SIZE = 20 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg"}


def document_file_extension(upload):
    normalized_name = upload.name.replace("\\", "/")
    return PurePosixPath(normalized_name).suffix.lower()


def validate_document_upload(upload):
    if upload.size > MAX_DOCUMENT_UPLOAD_SIZE:
        raise ValidationError("Tệp vượt quá giới hạn 20 MB.")

    extension = document_file_extension(upload)
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError("Chỉ chấp nhận tệp PDF, DOCX, XLSX, PNG, JPG hoặc JPEG.")

    try:
        signature = upload.read(8)
        upload.seek(0)

        if extension == ".pdf" and not signature.startswith(b"%PDF-"):
            raise ValidationError("Nội dung tệp không khớp với loại PDF.")
        if extension == ".png" and signature != b"\x89PNG\r\n\x1a\n":
            raise ValidationError("Nội dung tệp không khớp với loại PNG.")
        if extension in {".jpg", ".jpeg"} and not signature.startswith(b"\xff\xd8\xff"):
            raise ValidationError("Nội dung tệp không khớp với loại JPEG.")
        if extension in {".docx", ".xlsx"}:
            with ZipFile(upload) as archive:
                entries = set(archive.namelist())
            required_entries = (
                {"[Content_Types].xml", "word/document.xml"}
                if extension == ".docx"
                else {"[Content_Types].xml", "xl/workbook.xml"}
            )
            if not required_entries.issubset(entries):
                raise ValidationError(
                    f"Nội dung tệp không khớp với loại {extension[1:].upper()}."
                )
    except BadZipFile as exc:
        raise ValidationError("Tệp DOCX hoặc XLSX không phải gói Office hợp lệ.") from exc
    finally:
        upload.seek(0)
