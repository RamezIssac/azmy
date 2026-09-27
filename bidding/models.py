from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from extraction.models import LVItem
from projects.models import Project


class Provider(models.Model):
    """A subcontractor/supplier who may bid. Accounts are staff-created (v1)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="provider"
    )
    company = models.CharField(max_length=255)
    trade_codes = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("DIN 276 groups or trade labels, comma-separated"),
    )
    regions = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.company


class Bid(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SUBMITTED = "submitted", _("Submitted")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="bids")
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="bids")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "provider"], name="unique_bid_per_provider"
            )
        ]
        ordering = ["-submitted_at", "-created_at"]

    def __str__(self):
        return f"{self.provider} → {self.project} ({self.get_status_display()})"

    @property
    def total(self):
        from django.db.models import Sum, F

        return (
            self.items.filter(price__isnull=False, lv_item__menge__isnull=False)
            .aggregate(t=Sum(F("price") * F("lv_item__menge")))["t"]
        )

    @property
    def priced_count(self) -> int:
        return self.items.filter(price__isnull=False).count()

    def submit(self):
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])


class BidItem(models.Model):
    """One priced position. References the LV item by FK (OZ stays stable)."""

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name="items")
    lv_item = models.ForeignKey(LVItem, on_delete=models.CASCADE, related_name="bid_items")
    price = models.DecimalField(
        _("unit price (EP)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bid", "lv_item"], name="unique_biditem_per_lvitem"
            )
        ]

    def __str__(self):
        return f"{self.lv_item.oz} @ {self.price}"
