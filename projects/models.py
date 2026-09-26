import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .storage import private_storage


def document_upload_path(instance: "Document", filename: str) -> str:
    return (
        f"projects/{instance.document_set.project_id}"
        f"/set-{instance.document_set.version}/{filename}"
    )


class Project(models.Model):
    """A construction project (Bauvorhaben) we received documents for."""

    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(unique=True, max_length=280)
    address = models.CharField(_("address / site"), max_length=255, blank=True)
    client_name = models.CharField(_("client (Bauherr)"), max_length=255, blank=True)
    architect = models.CharField(_("planning / architect"), max_length=255, blank=True)
    bid_deadline = models.DateTimeField(_("bid deadline"), null=True, blank=True)
    execution_period = models.CharField(
        _("execution period"), max_length=255, blank=True
    )
    submission_place = models.CharField(
        _("submission place (Abgabeort)"), max_length=255, blank=True
    )
    notes = models.TextField(blank=True)

    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:240] or "project"
            slug = base
            n = 2
            while Project.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("projects:detail", kwargs={"slug": self.slug})

    def get_public_url(self):
        return reverse("projects:public", kwargs={"token": self.public_token})

    def publish(self):
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=["is_published", "published_at", "updated_at"])

    def unpublish(self):
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])

    @property
    def latest_set(self) -> "DocumentSet | None":
        return self.document_sets.order_by("-version").first()


class DocumentSet(models.Model):
    """A versioned bundle of documents for a project (addenda = new set)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="document_sets"
    )
    version = models.PositiveIntegerField()
    label = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version"], name="unique_set_version"
            )
        ]

    def __str__(self):
        return f"{self.project} — set v{self.version}"

    def save(self, *args, **kwargs):
        if not self.version:
            last = (
                DocumentSet.objects.filter(project=self.project)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
            )
            self.version = (last or 0) + 1
        super().save(*args, **kwargs)


class Document(models.Model):
    class DocType(models.TextChoices):
        LV = "lv", _("Leistungsverzeichnis (BOQ)")
        GAEB = "gaeb", _("GAEB file")
        PLAN = "plan", _("Plan / drawing")
        SPEC = "spec", _("Spec / other text")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        UPLOADED = "uploaded", _("Uploaded")
        PROCESSING = "processing", _("Processing")
        EXTRACTED = "extracted", _("Extracted — ready for review")
        MANUAL_QUEUE = "manual_queue", _("Queued for manual processing")
        APPROVED = "approved", _("Approved")
        FAILED = "failed", _("Failed")

    document_set = models.ForeignKey(
        DocumentSet, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to=document_upload_path, storage=private_storage)
    original_filename = models.CharField(max_length=255)
    doc_type = models.CharField(
        max_length=10, choices=DocType.choices, default=DocType.LV
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPLOADED
    )
    page_count = models.PositiveIntegerField(null=True, blank=True)
    text_layer_ok = models.BooleanField(default=True)
    run_judge = models.BooleanField(
        default=True, help_text=_("Run a second LLM as judge after extraction")
    )
    error_message = models.TextField(blank=True)
    extraction_report = models.JSONField(
        default=dict, blank=True, help_text=_("Parser/LLM stats and judge notes")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["doc_type", "original_filename"]

    def __str__(self):
        return f"{self.original_filename} ({self.get_doc_type_display()})"

    @property
    def project(self) -> Project:
        return self.document_set.project
