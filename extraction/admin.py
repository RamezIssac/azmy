from django.contrib import admin

from .models import LV, LVItem, LVSection


class LVSectionInline(admin.TabularInline):
    model = LVSection
    extra = 0
    fields = ["kind", "number", "title", "ordering"]


@admin.register(LV)
class LVAdmin(admin.ModelAdmin):
    list_display = ["__str__", "number", "gewerk", "din276_group", "item_count"]
    inlines = [LVSectionInline]


@admin.register(LVItem)
class LVItemAdmin(admin.ModelAdmin):
    list_display = ["oz", "short_text", "menge", "einheit", "confidence", "source"]
    list_filter = ["source", "einheit", "is_reviewed"]
    search_fields = ["oz", "short_text", "long_text"]
    readonly_fields = ["oz"]
