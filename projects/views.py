from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from extraction.models import LV, LVItem
from extraction.tasks import enqueue_extraction

from .models import Document, DocumentSet, Project


# ---------------------------------------------------------------- staff area


@staff_member_required
def dashboard(request):
    projects = (
        Project.objects.prefetch_related("document_sets__documents")
        .order_by("-created_at")
    )
    rows = []
    for project in projects:
        latest = project.latest_set
        docs = list(latest.documents.all()) if latest else []
        rows.append(
            {
                "project": project,
                "docs": docs,
                "items": LVItem.objects.filter(
                    section__lv__document__document_set__project=project
                ).count(),
            }
        )
    return render(request, "projects/dashboard.html", {"rows": rows})


@staff_member_required
def project_create(request):
    if request.method == "POST":
        project = Project.objects.create(
            name=request.POST.get("name", "").strip() or "Unbenanntes Projekt",
            address=request.POST.get("address", "").strip(),
            client_name=request.POST.get("client_name", "").strip(),
            created_by=request.user,
        )
        messages.success(request, f"Projekt „{project.name}“ angelegt.")
        return redirect(project)
    return render(request, "projects/project_form.html")


@staff_member_required
def project_detail(request, slug):
    project = get_object_or_404(Project, slug=slug)
    sets = project.document_sets.prefetch_related("documents__lv")
    processing = any(
        d.status in (Document.Status.UPLOADED, Document.Status.PROCESSING)
        for s in project.document_sets.all()
        for d in s.documents.all()
    )
    return render(
        request,
        "projects/project_detail.html",
        {"project": project, "sets": sets, "processing": processing},
    )


@staff_member_required
@require_POST
def upload_documents(request, slug):
    project = get_object_or_404(Project, slug=slug)
    files = request.FILES.getlist("files")
    if not files:
        messages.error(request, "Keine Dateien ausgewählt.")
        return redirect(project)
    doc_type = request.POST.get("doc_type", Document.DocType.LV)
    doc_set = DocumentSet.objects.create(project=project, uploaded_by=request.user)
    for f in files:
        guessed = doc_type
        name = f.name.lower()
        if name.endswith((".x83", ".x31", ".xml")):
            guessed = Document.DocType.GAEB
        Document.objects.create(
            document_set=doc_set,
            file=f,
            original_filename=f.name,
            doc_type=guessed,
        )
    messages.success(
        request, f"{len(files)} Datei(en) als Set v{doc_set.version} hochgeladen."
    )
    return redirect(project)


@staff_member_required
@require_POST
def process_document(request, pk):
    document = get_object_or_404(Document, pk=pk)
    enqueue_extraction(document)
    messages.info(request, f"Extraktion gestartet: {document.original_filename}")
    return redirect(document.project)


@staff_member_required
def document_file(request, pk):
    """Staff-gated delivery of private tender documents."""
    document = get_object_or_404(Document, pk=pk)
    return FileResponse(
        document.file.open("rb"),
        content_type="application/pdf",
        filename=document.original_filename,
    )


@staff_member_required
@require_POST
def publish_project(request, slug):
    project = get_object_or_404(Project, slug=slug)
    approved = LV.objects.filter(
        document__document_set__project=project,
        document__status=Document.Status.APPROVED,
    ).exists()
    if not approved:
        messages.error(
            request, "Mindestens ein LV muss geprüft/freigegeben sein vor Veröffentlichung."
        )
        return redirect(project)
    project.publish()
    messages.success(request, "Projekt veröffentlicht.")
    return redirect(project)


@staff_member_required
@require_POST
def unpublish_project(request, slug):
    project = get_object_or_404(Project, slug=slug)
    project.unpublish()
    messages.info(request, "Veröffentlichung zurückgezogen.")
    return redirect(project)


# ---------------------------------------------------------------- public area


def _published_project(token) -> Project:
    project = get_object_or_404(Project, public_token=token, is_published=True)
    return project


def _public_lv_tree(project: Project) -> list[dict]:
    lvs = (
        LV.objects.filter(
            document__document_set__project=project,
            document__status=Document.Status.APPROVED,
        )
        .prefetch_related("sections__items")
        .order_by("number")
    )
    result = []
    for lv in lvs:
        sections = list(lv.sections.all())
        children: dict[int | None, list] = {}
        for sec in sections:
            children.setdefault(sec.parent_id, []).append(sec)

        def sec_dict(sec) -> dict:
            return {
                "number": sec.number,
                "kind": sec.kind,
                "title": sec.title,
                "items": [
                    {
                        "oz": it.oz,
                        "short_text": it.short_text,
                        "long_text": it.long_text,
                        "menge": float(it.menge) if it.menge is not None else None,
                        "einheit": it.einheit,
                        "unit_price": float(it.unit_price) if it.unit_price is not None else None,
                        "total_price": float(it.total_price) if it.total_price is not None else None,
                        "din276_group": it.din276_group,
                    }
                    for it in sec.items.all()
                ],
                "sections": [sec_dict(c) for c in children.get(sec.id, [])],
            }

        result.append(
            {
                "number": lv.number,
                "gewerk": lv.gewerk,
                "title": lv.title,
                "din276_group": lv.din276_group,
                "sections": [sec_dict(s) for s in children.get(None, [])],
            }
        )
    return result


def _public_payload(project: Project) -> dict:
    return {
        "name": project.name,
        "address": project.address,
        "client_name": project.client_name,
        "architect": project.architect,
        "bid_deadline": project.bid_deadline.isoformat() if project.bid_deadline else None,
        "execution_period": project.execution_period,
        "lvs": _public_lv_tree(project),
    }


def public_project(request, token):
    project = _published_project(token)
    return render(
        request,
        "projects/public.html",
        {"project": project, "lvs": _public_lv_tree(project)},
    )


def public_project_api(request, token):
    project = _published_project(token)
    return JsonResponse(_public_payload(project))
