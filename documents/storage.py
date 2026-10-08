from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDocumentStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=Path(settings.BASE_DIR) / "private_uploads",
            base_url=None,
        )

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Private document files have no public URL.")
