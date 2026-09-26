from django.contrib import admin

from .models import Document, DocumentSet, Project


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    readonly_fields = ["status", "page_count", "created_at"]
    fields = ["original_filename", "doc_type", "status", "page_count", "created_at"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "client_name", "is_published", "created_at"]
    list_filter = ["is_published"]
    search_fields = ["name", "client_name", "address"]
    readonly_fields = ["public_token", "published_at"]


@admin.register(DocumentSet)
class DocumentSetAdmin(admin.ModelAdmin):
    list_display = ["project", "version", "label", "uploaded_by", "created_at"]
    inlines = [DocumentInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "doc_type", "status", "page_count"]
    list_filter = ["doc_type", "status"]
    search_fields = ["original_filename"]
