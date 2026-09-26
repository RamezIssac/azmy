from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from projects.models import Document

from .models import LVItem


@staff_member_required
def review_document(request, pk):
    document = get_object_or_404(
        Document.objects.select_related("document_set__project"), pk=pk
    )
    lv = getattr(document, "lv", None)
    sections = (
        lv.sections.prefetch_related("items", "children").all() if lv else []
    )
    top_sections = [s for s in sections if s.parent_id is None]
    stats = {}
    if lv:
        items = LVItem.objects.filter(section__lv=lv)
        stats = {
            "items": items.count(),
            "reviewed": items.filter(is_reviewed=True).count(),
            "low_confidence": items.filter(confidence__lt=0.9).count(),
        }
    return render(
        request,
        "extraction/review.html",
        {
            "document": document,
            "lv": lv,
            "top_sections": top_sections,
            "stats": stats,
        },
    )


@staff_member_required
def item_edit(request, pk):
    item = get_object_or_404(LVItem, pk=pk)
    if request.method == "POST":
        for field in ["short_text", "long_text", "einheit", "din276_group"]:
            if field in request.POST:
                setattr(item, field, request.POST[field])
        for field in ["menge", "unit_price", "total_price"]:
            if field in request.POST:
                raw = request.POST[field].strip().replace(",", ".")
                setattr(item, field, raw or None)
        item.is_reviewed = True
        item.save()
        return render(request, "extraction/_item_row.html", {"item": item})
    if request.GET.get("cancel"):
        return render(request, "extraction/_item_row.html", {"item": item})
    return render(request, "extraction/_item_edit.html", {"item": item})


@staff_member_required
@require_POST
def item_toggle_reviewed(request, pk):
    item = get_object_or_404(LVItem, pk=pk)
    item.is_reviewed = not item.is_reviewed
    item.save(update_fields=["is_reviewed"])
    return render(request, "extraction/_item_row.html", {"item": item})


@staff_member_required
@require_POST
def approve_document(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not hasattr(document, "lv"):
        messages.error(request, "Nur extrahierte LVs können freigegeben werden.")
    else:
        document.status = Document.Status.APPROVED
        document.save(update_fields=["status", "updated_at"])
        messages.success(
            request, f"„{document.original_filename}“ freigegeben (approved)."
        )
    return redirect(document.project)
