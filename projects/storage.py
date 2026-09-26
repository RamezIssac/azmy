from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Stores tender documents outside MEDIA_ROOT.

    Files are served exclusively through the staff-gated Django view at
    /files/<path> (see projects.views.serve_private_file) — never via the
    web server's /media/ alias. base_url makes file.url resolve to that view
    everywhere (admin links, templates).
    """

    def __init__(self):
        super().__init__(location=settings.PRIVATE_ROOT, base_url="/files/")


private_storage = PrivateStorage()
