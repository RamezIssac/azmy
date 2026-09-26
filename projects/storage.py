from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Stores tender documents outside MEDIA_ROOT.

    Files are served exclusively through the staff-gated Django view —
    never via the web server's /media/ alias.
    """

    def __init__(self):
        super().__init__(location=settings.PRIVATE_ROOT)


private_storage = PrivateStorage()
