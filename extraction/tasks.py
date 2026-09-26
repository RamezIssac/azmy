"""RQ entry points. Sync fallback keeps dev/test Redis-free."""

from __future__ import annotations

from django.conf import settings


def run_extraction(document_id: int):
    from extraction.services.pipeline import extract_document
    from projects.models import Document

    document = Document.objects.get(pk=document_id)
    return extract_document(document)


def enqueue_extraction(document):
    if getattr(settings, "RQ_ENABLED", False):
        import django_rq

        django_rq.enqueue(run_extraction, document.pk)
        document.status = document.Status.PROCESSING
        document.save(update_fields=["status", "updated_at"])
    else:
        run_extraction(document.pk)
