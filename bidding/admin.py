from django.contrib import admin

from .models import Bid, BidItem, Provider


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["company", "user", "trade_codes", "regions"]
    search_fields = ["company", "user__email"]


class BidItemInline(admin.TabularInline):
    model = BidItem
    extra = 0
    fields = ["lv_item", "price", "note"]


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ["provider", "project", "status", "priced_count", "submitted_at"]
    list_filter = ["status", "project"]
    inlines = [BidItemInline]
