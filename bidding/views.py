from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from extraction.models import LV, LVItem
from projects.models import Project

from .models import Bid, BidItem, Provider


def _provider_or_none(request):
    return getattr(request.user, "provider", None)


# ------------------------------------------------------------------ provider portal


@login_required
def portal(request):
    provider = _provider_or_none(request)
    if provider is None:
        return render(request, "bidding/no_provider.html", status=403)
    projects = Project.objects.filter(is_published=True).order_by("-published_at")
    my_bids = {b.project_id: b for b in provider.bids.all()}
    rows = [(p, my_bids.get(p.pk)) for p in projects]
    return render(
        request,
        "bidding/portal.html",
        {"provider": provider, "rows": rows},
    )


@login_required
def bid_editor(request, slug):
    """The provider's bid form: every LV position with a price field."""
    provider = _provider_or_none(request)
    if provider is None:
        return HttpResponseForbidden()
    project = get_object_or_404(Project, slug=slug, is_published=True)
    lvs = list(
        LV.objects.filter(
            document__document_set__project=project,
            document__status="approved",
        ).prefetch_related("sections__items")
    )
    if not lvs:
        messages.error(request, "Dieses Projekt hat noch keine freigegebenen LVs.")
        return redirect("bidding:portal")

    bid, _ = Bid.objects.get_or_create(project=project, provider=provider)
    if bid.status == Bid.Status.SUBMITTED:
        messages.info(request, "Angebot bereits abgegeben.")
        return redirect("bidding:portal")

    if request.method == "POST":
        with transaction.atomic():
            for item in LVItem.objects.filter(section__lv__in=lvs):
                raw = request.POST.get(f"price_{item.pk}", "").strip()
                note = request.POST.get(f"note_{item.pk}", "").strip()
                if not raw and not note:
                    continue
                price = None
                if raw:
                    try:
                        price = float(raw.replace(".", "").replace(",", "."))
                    except ValueError:
                        messages.error(
                            request, f"Ungültiger Preis bei {item.oz}: „{raw}“"
                        )
                        return redirect(request.path)
                BidItem.objects.update_or_create(
                    bid=bid, lv_item=item, defaults={"price": price, "note": note}
                )
            bid.note = request.POST.get("bid_note", "").strip()
            bid.save(update_fields=["note"])
            if "submit" in request.POST:
                if bid.priced_count == 0:
                    messages.error(request, "Keine Position bepreist — nicht abgegeben.")
                    return redirect(request.path)
                bid.submit()
                messages.success(request, "Angebot abgegeben. Vielen Dank!")
                return redirect("bidding:portal")
        messages.success(request, "Entwurf gespeichert.")
        return redirect(request.path)

    existing = {i.lv_item_id: i for i in bid.items.all()}

    def tree(section):
        return {
            "title": f"{section.number} {section.title}",
            "items": [
                {"item": it, "bid_item": existing.get(it.pk)} for it in section.items.all()
            ],
            "children": [tree(c) for c in section.children.all()],
        }

    lv_trees = [
        {"lv": lv, "sections": [tree(s) for s in lv.sections.all() if s.parent_id is None]}
        for lv in lvs
    ]
    return render(
        request,
        "bidding/bid_editor.html",
        {"project": project, "lv_trees": lv_trees, "bid": bid},
    )


# ------------------------------------------------------------------ staff: leveling


@staff_member_required
def leveling(request, slug):
    """Side-by-side bid comparison per LV section. Gaps and outliers flagged."""
    project = get_object_or_404(Project, slug=slug)
    bids = list(
        Bid.objects.filter(project=project, status=Bid.Status.SUBMITTED)
        .select_related("provider")
        .prefetch_related("items")
    )
    price_map = {  # lv_item_id -> {bid_id: price}
    }
    for bid in bids:
        for item in bid.items.all():
            if item.price is not None:
                price_map.setdefault(item.lv_item_id, {})[bid.pk] = float(item.price)

    lvs = LV.objects.filter(
        document__document_set__project=project, document__status="approved"
    ).prefetch_related("sections__items")

    sections_out = []
    for lv in lvs:
        for section in lv.sections.all():
            rows = []
            for item in section.items.all():
                prices = price_map.get(item.pk, {})
                values = list(prices.values())
                lo = min(values) if values else None
                hi = max(values) if values else None
                spread = (hi / lo - 1) if lo and hi and lo > 0 else 0
                rows.append(
                    {
                        "item": item,
                        "prices": prices,  # bid_id -> price
                        "low": lo,
                        "high": hi,
                        "spread_pct": round(spread * 100),
                        "gap_bids": [b.pk for b in bids if b.pk not in prices],
                    }
                )
            if rows:
                sections_out.append(
                    {"title": f"{lv.number} · {section.number} {section.title}", "rows": rows}
                )
    return render(
        request,
        "bidding/leveling.html",
        {"project": project, "bids": bids, "sections": sections_out},
    )
