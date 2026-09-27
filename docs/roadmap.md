# azmy / bau_match — Roadmap & Decision Log

The single source of truth for where we are and what's next.
Dated brainstorms live in `docs/brainstorms/`; living specs: `phase-1-design.md`,
`phase-2-design.md`, `deployment-plan.md`; lavish review artifacts in `.lavish/`.
This file is updated at every sprint boundary.

_Last updated: 2026-09-27 (after Phase 2 shipped)_

---

## North star

> Not "AI reads construction PDFs". **The machine-readable rail on which construction
> tenders become queryable — and machines bid on them.** API is the product; UI is a client.

## Status at a glance

| Phase | Scope | Status |
|---|---|---|
| 1 | PDF → structured LV, review UI, publish + read API, GAEB import | ✅ live (2026-09-26) |
| 2 | 2A multi-doc intelligence (vision OCR, auto-triage, doc briefs) + 2C web bidding (portal, bid editor, leveling) + design system + partner manual | ✅ live (2026-09-27) |
| 3 | Agent substrate (MCP, API keys), ask_question/RAG, EOI publish, provider onboarding | 🔜 next sprint |
| 4 | Marketplace: reputation, pricing intelligence, success fees | 🔮 later |

Live: **https://azmy.raenterprises.de** · Manual for partners: **/manual/**

---

## Phase 3 — next sprint (scoped 2026-09-27)

Order of attack + rationale:

1. **Publish without LV** — document-only projects (EOI like Haus der Gesundheit) become
   shareable. Gate becomes: ≥1 extracted document + explicit staff confirm.
   _Small, unblocks the real EOI project already uploaded._
2. **SMTP + provider invitations** — real email backend via `extra_env`; invite flow for
   providers; bid confirmations. _Needed before partners onboard real bidders._
3. **MCP server + provider API keys** (the moat) — tools: `search_projects`, `get_boq`,
   `get_item_detail`, `submit_bid` (thin wrapper over the Phase 2 bid schema).
   Hashed keys with scopes (`read`/`bid`), rate limits, full audit log.
4. **ask_question (RAG)** — chunk + embed narrative front matter + non-LV docs (+ OCR text);
   answers with page citations. numpy cosine in-app first; pgvector when chunks > ~50k.
   _Position pages stay out of RAG: they are structured rows already (review decision)._
5. **Provider self-signup** — with staff approval step; today: staff-created (locked decision).
6. **Addenda diffing** — DocumentSet versions diffed; changes pushed to bidders
   (`?since=` feed first, webhooks when flaky-free).

Explicitly NOT in phase 3: drawing takeoff (measurement off plans), award workflow,
payments, GC portal monitoring (phase 4 candidate).

## Phase 4 — later

- Provider reputation (bid accuracy, award rate, completion) → matching scores.
- Pricing intelligence: anonymized bid aggregates → market price indices per trade/region.
  _The data-moat product; only possible because bids are structured against our OZ schema._
- Revenue: per-project analysis fee now; success fees once trust + volume exist.
- GC portal monitoring (supply-side scanning — idea from session 2, parked).
- Drawing takeoff v2 (vector PDF / DWG measurement).

---

## Decision log (locked)

### Product & scope
| When | Decision | Where reviewed |
|---|---|---|
| 09-26 | Phase 1 = single-player wedge: upload → structured LV → publish. Marketplace later. | brainstorm S1 |
| 09-26 | Internal uploads only; single-tenant; human-gated publish (trust story) | brainstorm S3 |
| 09-26 | GAEB import in v1 (doubles as parser benchmark); scans queue manually | brainstorm S3 |
| 09-26 | Accept all document types; LV extracted, rest stored (+intel since P2) | brainstorm S3 |
| 09-26 | Publish = token link + read-only JSON API from day one (Phase 3 MCP wraps it) | brainstorm S3 |
| 09-27 | Phase 2 = 2A + 2C **web only**; agent substrate → Phase 3 | chat + phase-2 doc |
| 09-27 | Bid schema agent-compatible from day one (BidItem → LVItem by OZ) | architecture artifact |
| 09-27 | RAG deferred to Phase 3; LV position pages are NOT RAG-indexed (already structured) | lavish architecture review |
| 09-27 | Providers staff-created first; self-signup later | lavish architecture review ("Agree") |
| 09-27 | `source_url` on Project; set from tender portals (berlin.de) | chat |

### Tech
| When | Decision |
|---|---|
| 09-26 | pypdfium2 for text layer (wheel-only, deploy-safe); deterministic parser first, LLM for semantics |
| 09-26 | OCR → vision-LLM via OpenRouter (no tesseract); resumable sidecar cache; failures never cached |
| 09-26 | rambo contract: POSTGRES_* env, REDIS_URL, override=True dotenv, private files off /media |
| 09-27 | LLM routing: per-task `OPENROUTER_MODEL_*` env, comma-separated fallback chains, free tier first + gemini-2.5-flash backstop, 429 backoff. Judge failures stay advisory |
| 09-27 | No channels/websockets yet (htmx polling); daphne kept in requirements (rambo provisions the unit unconditionally) |
| 09-27 | Design: B (Linear-grade base) + C (agent accents) + A (blueprint spice); agent console SLEEPS until real traffic; `azmy_` wordmark |

### Ops learnings (details in deployment-plan.md)
- rasystem26 redis_bind seed bug fixed (was breaking other apps too).
- GitHub deploy keys are per-repo: azmy has its own (`git@azmy:…`).
- rambo runs from worktree `~/work_own/rambo-hosting` (branch `hosting`), symlinks into main checkout.
- Seed via `manage.py shell` as root → chown to deploy after (worker sidecar writes).

## Open questions

1. **EOI publish gate** — publish document-only projects? (leaning yes; planned as P3 item 1)
2. **Design tuning** — accent color, staff theme default, wordmark: unanswered in lavish
   (defaults applied: indigo / light / `azmy_`). Answer in `.lavish/design-direction.html` anytime.
3. **Manual language** — German now; add English for international partners?
4. **Demo provider accounts on prod** (trockenbau-mueller / bedia) — keep as demo or replace with first real bidder?
