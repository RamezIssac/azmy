from django.db import models
from django.utils.translation import gettext_lazy as _

from projects.models import Document


class LV(models.Model):
    """A Leistungsverzeichnis (bill of quantities) extracted from a document."""

    document = models.OneToOneField(
        Document, on_delete=models.CASCADE, related_name="lv"
    )
    number = models.CharField(max_length=20, blank=True, help_text=_("e.g. 11"))
    gewerk = models.CharField(max_length=255, blank=True, help_text=_("e.g. Trockenbauarbeiten"))
    title = models.CharField(max_length=255, blank=True)
    din276_group = models.CharField(
        max_length=10, blank=True, help_text=_("DIN 276 cost group, e.g. 390")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "LV"
        verbose_name_plural = "LVs"

    def __str__(self):
        return f"LV {self.number} {self.gewerk}".strip()

    @property
    def item_count(self) -> int:
        return LVItem.objects.filter(section__lv=self).count()


class LVSection(models.Model):
    """A node in the LV hierarchy (LV / Titel / Untertitel / …)."""

    class Kind(models.TextChoices):
        LV = "lv", "LV"
        TITEL = "titel", "Titel"
        UNTERTITEL = "untertitel", "Untertitel"
        ABSCHNITT = "abschnitt", "Abschnitt"

    lv = models.ForeignKey(LV, on_delete=models.CASCADE, related_name="sections")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    number = models.CharField(max_length=20)
    title = models.CharField(max_length=500, blank=True)
    ordering = models.PositiveIntegerField(default=0)
    page_start = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return f"{self.number} {self.title}".strip()


class LVItem(models.Model):
    """A single position (line item) of an LV."""

    class Source(models.TextChoices):
        PDF = "pdf", "PDF extraction"
        GAEB = "gaeb", "GAEB import"
        MANUAL = "manual", "Manual entry"

    section = models.ForeignKey(
        LVSection, on_delete=models.CASCADE, related_name="items"
    )
    number = models.CharField(max_length=20, help_text=_("Position number, e.g. 290"))
    oz = models.CharField(
        max_length=60, db_index=True, help_text=_("Ordnungszahl, e.g. 03.01.0290")
    )
    short_text = models.TextField(blank=True)
    long_text = models.TextField(blank=True)
    menge = models.DecimalField(
        _("quantity"), max_digits=14, decimal_places=3, null=True, blank=True
    )
    einheit = models.CharField(_("unit"), max_length=20, blank=True)
    unit_price = models.DecimalField(
        _("unit price (EP)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    total_price = models.DecimalField(
        _("total price (GP)"), max_digits=16, decimal_places=2, null=True, blank=True
    )
    din276_group = models.CharField(max_length=10, blank=True)
    confidence = models.FloatField(default=1.0)
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.PDF
    )
    is_reviewed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return f"{self.oz} {self.short_text[:60]}".strip()
