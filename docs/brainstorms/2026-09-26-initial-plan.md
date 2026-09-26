# 2026-09-26 — Initial Plan (agent-first construction tendering)

## Product concept

We receive construction projects as PDFs → analyze them into **quality & quantity items**
(structured BOQ / German *Leistungsverzeichnis*) → expose the result so that **provider
agents** (subcontractors' / suppliers' AI agents) can query it and apply for parts of the project.

One-sentence positioning:
> We're not building AI that helps humans read construction PDFs. We're building the
> machine-readable marketplace where construction work gets matched to the agents that
> price and bid it.

---

## 1. Cost–Benefit Analysis

### The pain we monetize
- Quantity takeoff = 30–50% of estimating time; days of skilled labor per project.
- GCs get too few bids per package (typically 3–5, same usual suspects).
- Providers waste effort bidding on projects that don't fit trade/region/capacity.
- Bid leveling is manual (bids arrive as random PDFs/Excel).

### Benefits (→ KPIs / sales pitch)
| Metric | Baseline today | Target |
|---|---|---|
| PDF → structured BOQ | 2–5 days | < 1 hour + human review |
| Bids per package | 3–5 | 10–15 (agent-driven) |
| Provider cost-per-bid | High (manual read) | ~zero (agent filters) |
| Bid leveling | Days | Instant (same schema in/out) |
| Award cycle time | Weeks | Days |

### Costs / risks (honest list)
1. **Extraction accuracy & liability** — wrong quantity → wrong bid → dispute. Needs
   confidence scores, provenance, human-in-the-loop. Biggest ongoing cost.
2. **Cold start / two-sided problem** — solved via single-player wedge (below).
3. **LLM/OCR pipeline cost per page** — trivial vs. one awarded subcontract.
4. **Slow, conservative sales cycle** in construction.
5. **Incumbents adding AI** (Procore, BuildingConnected, Togal.AI, Kreo, PlanRadar) —
   we cannot out-feature them; we out-protocol them.

### Revenue stack (over time)
1. Per-project analysis fee (GC pays per uploaded doc set) — first dollar.
2. Success fee on awarded subcontracts (% of value).
3. **Agent API metering** — provider agents pay per query/access/subscription (agent-first-native revenue).
4. **Pricing intelligence** — aggregated anonymized bid data → market price indices per trade/region (the data-moat product).
5. SaaS tender dashboard for GCs.

### Verdict
Worth doing IF cold start is solved with a wedge: **start as a single-player tool** —
"upload your project PDFs → get a structured, coded BOQ + shareable tender link" —
valuable to one GC/estimating office with zero network. Marketplace grows out of that supply.

---

## 2. Competitive advantage — why agent-first is the moat

Everyone else builds a **copilot for a human estimator** (crowded, incumbent-owned).
Our bet: the buyer side is being automated too, and there is **no machine-readable
substrate** for procurement agents — tenders live as PDFs behind logins and email chains.

Uniqueness stack:
1. **API is the product; UI is just a client.** MCP server + REST API as first-class
   citizens. "Stripe for construction tendering."
2. **We own the schema.** Normalize every item to standard trade codes
   (DIN 276 / VOB / GAEB in Germany; MasterFormat/UniFormat internationally).
   Schema ownership = switching costs.
3. **Structured bids → instant leveling.** Bids come back against OUR normalized items →
   automatic comparison, anomaly detection, scope-gap flags. Incumbents can't retrofit this.
4. **Data network effect / reputation layer.** Bid accuracy, award rates, completion data,
   real market prices per trade/region — compounding, un-scrapable.
5. **Provenance & trust as a feature.** Every extracted quantity links to the exact
   page/region of the source PDF, with confidence scores. "Verifiable AI extraction."

---

## 3. Techniques (high level)

### Layer A — Ingestion: PDFs → structured BOQ
1. Page triage classifier (drawing vs spec vs BOQ table vs scanned).
2. Text/table extraction for spec books and BOQ PDFs — LLM + vision → structured JSON. 80% of the value, tractable now.
3. Drawing takeoff (measuring off plans: vector parsing, scale detection, symbol counting) — **defer to v2**.
4. Trade-code mapping: embeddings + LLM classification against DIN 276 / GAEB / MasterFormat lists.
5. Human-in-the-loop review UI: confidence heatmap, PDF ↔ item side-by-side with citations; corrections become eval data (quality flywheel).

### Layer B — Agent substrate (the differentiator)
1. MCP server tools: `search_projects`, `get_boq`, `get_item_detail`, `ask_question` (RAG over source PDFs w/ page citations), `submit_bid`.
2. REST API + OAuth client credentials, rate limits, full audit log (needed for disputes).
3. Event push: webhooks/feed per provider — "new project matching your profile."
4. Versioned bid schema + addenda versioning (doc revisions → diffable events pushed to subscribed agents).

### Layer C — Matching & marketplace
1. Provider profiles: trades (coded), regions, capacity, certifications — structured filters first, embeddings second.
2. Bid leveling engine: outlier flags, scope-gap detection (bid 9 of 12 items → flag).
3. Reputation: award outcomes + completion feedback → matching scores.

### Layer D — Trust (cross-cutting)
- Per-field confidence, provenance links, human sign-off gate before a project goes "live" to agents.

### Phasing (each phase independently valuable)
| Phase | Deliverable | Value unlocked |
|---|---|---|
| **1** | Ingestion → structured coded BOQ + review UI + shareable tender link | Single-player tool for GCs/estimators. Revenue day one. |
| **2** | Provider portal + API keys + MCP server + structured bid submission | Agent-first differentiator. Automatic leveling. |
| **3** | Marketplace: matching, reputation, pricing intelligence | Network effects + data moat. |

### Stack fit
Django + slick_reporting (leveling/analytics = group-by/crosstab problems), django-rq
for extraction workers, channels for live events, MCP server as a separate service
alongside Daphne. Nothing exotic for v1.

### Sharpest strategic question
**Where does supply come from?** One pilot GC willing to run a real tender through the
platform de-risks more than any technical decision.

---

## Additions from session 2 (same day)

### New pipeline idea: supply-side monitoring
A pipeline that **scans / monitors GCs for new projects** (public tender portals,
GC websites, email digests) and pulls projects into the platform proactively instead of
waiting for uploads. Sources to evaluate later: evergabe.de, vergabe24, DTAD,
subreport, GC/developer tender pages. Status: **idea captured, phasing TBD** (likely 1.5).

### Sample document analyzed: `rockenbauarbeiten.pdf`
- 90 pages, A4, clean text layer (no OCR needed).
- German **Leistungsverzeichnis (LV) für Trockenbauarbeiten** — drywall works.
- Project: Neubau von 6 MFH mit 160 Wohneinheiten, Franz-Mehring-Platz 6, Berlin.
- Structure follows VOB convention:
  - Cover (Bauherr, Planung, Bauleitung/Ausschreibung, Abgabeort)
  - Inhaltsverzeichnis
  - 1. ZTV (Zusätzliche Technische Vertragsbedingungen)
  - 2. Allgemeine Baubeschreibung
  - 3. Gewerkespezifische Baubeschreibung
  - 4. Grundstück/Baustelle
  - 5. Ausführung
  - 6. Technische Vorbemerkungen Trockenbauarbeiten
  - → then the priced **Positionen** (line items) with OZ / Menge / ME / EP / GP
- Confirms: **market = Germany**, vocabulary = OZ/Position/Titel/Gewerk,
  standards to respect = **VOB/B, DIN 276 (cost groups), GAEB (data exchange)**.
- Note: GAEB files (DA83/DA84/X83...) are already structured — supporting GAEB import
  is a cheap win AND an accuracy benchmark for our PDF extractor.

### Decision
**Phase 1 is GO.** System design session completed (see `docs/phase-1-design.md` for the living spec).

---

## Session 3 — Phase 1 design decisions (locked)

| # | Question | Decision |
|---|---|---|
| Q1 | Who uploads | **Internal staff only** (we onboard pilot projects manually) |
| Q2 | Who reviews extraction | **Us, initially** — but review UI must be *very polished* OR backed by a **second LLM as judge/corrector** |
| Q3 | Tenancy | **Single-tenant** for Phase 1 |
| Q4 | Doc types in scope | **Accept all** — extract items from LV; store + RAG-index plans/specs for later `ask_question` |
| Q5 | GAEB import | **Yes, in v1** — doubles as ground-truth accuracy benchmark for the PDF extractor |
| Q6 | Scanned PDFs (no text layer) | **Queue for manual processing**, no OCR route in v1 |
| Q7 | Data schema | Approved as proposed (Project → DocumentSet → LV per Gewerk → section tree → Position w/ OZ, short/long text, Menge, Einheit, EP/GP, DIN 276 group, confidence, page refs) |
| Q8 | Extract prices when present | *Skipped → decided by default:* **yes, extract when present** (valuable data; provider bids stay Phase 2) |
| Q9 | Extraction flow | Hybrid engine (deterministic parse → LLM structure/semantics → vision fallback) + **human-gated publish** (nothing goes live without approval — our trust story) |
| Q10 | LLM provider | **OpenRouter** for now; concrete model assignments decided later per task |
| Q11 | "Published" means | **Shareable read link + read-only JSON API from day one** (the API the Phase 2 MCP server will wrap) |
| Q12 | Versioning/addenda | *Skipped → decided by default:* **store versions, defer diffing** |
| Q13 | GC scanning/monitoring pipeline | **Post-v1** (idea captured in Session 2) |
