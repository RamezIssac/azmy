# 2026-09-27 — Design directions (UI/UX proposals)

Current state: functional Bootstrap 5 default look, CDN-loaded, no identity.
Goal: a distinctive, credible product look. Three directions, then a recommendation.

Audiences to serve, in priority order:
1. **Staff/reviewers** (daily workbench — review UI is the most-used screen)
2. **Providers' humans** (public tender page — the shareable artifact)
3. **Agents** (they don't see pixels — but the public page should *advertise* the
   machine surface; it is the brand)

---

## Direction A — "Baustelle Industrial" (domain-native identity)

Blueprint aesthetic: DIN 1451 or Archivo type, blueprint grid backgrounds,
construction orange `#FF6B00` + anthracite + concrete gray, hazard-stripe accents
reserved for gates/approvals (publish, approve). Dashboard = site signboards
(Bauschild) per project. Review UI = "Prüfstand". Public tender page = official
notice board with QR code for the API endpoint.

- **Signal:** unmistakably German construction. Memorable, ownable.
- **Risk:** kitsch if overdone; grids fight dense tables.
- **Cost:** medium (custom CSS theme, some illustration).

## Direction B — "Linear-grade SaaS" (product credibility)

Inter/Geist grotesk, zinc/white palette, one accent (electric blue `#2563EB` or
signal green), big whitespace, calm dense tables with tabular numerals, status
pills, skeleton loaders, ⌘K palette, full keyboard flow in the review workbench
(j/k positions, e edit, x mark reviewed). Three-pane review: PDF | section tree |
item detail.

- **Signal:** "serious professional tool" — reads instantly to anyone who has used
  Linear/Stripe/Vercel. Fastest path to looking expensive.
- **Risk:** looks like every other SaaS; identity must come from content, not skin.
- **Cost:** low (Bootstrap 5.3 + CSS variables + Inter + focused components).

## Direction C — "Bloomberg terminal for tenders" (agent-native brand)

Dark-mode-first operations console: monospace numerals (JetBrains Mono), dense
grids, and a **live activity stream** as the centerpiece — every agent query, every
bid, every publish event ticks by ("agent drywall-gmbh-bot queried LV 11 · 12s ago").
Public tender page shows a "For agents" block with the MCP endpoint, OpenAPI link,
and a copyable JSON sample — the machine surface, worn proudly.

- **Signal:** this is the marketplace where machines trade — nobody in construction
  shows this. Directly performs the agent-first positioning.
- **Risk:** dark terminals can intimidate conservative GC staff; mitigate with
  light document views and using the stream as an accent, not the whole UI.
- **Cost:** medium-high (needs the event feed to be real — Phase 2B provides it).

---

## Recommendation (mine)

**B as the base, C accents as the differentiator, A only as spice.**
Build the Linear-grade workbench now (it makes daily review fast), add the live
agent-activity stream the moment Phase 2B events exist (it is the brand), and steal
A's hazard-stripe only for the approve/publish gate and the Bauschild project cards.

### Concrete first pass (independent of direction)

1. Inter + JetBrains Mono (tabular-nums for Menge/EP/GP), self-hosted via staticfiles.
2. Status color system: one semantic palette used everywhere
   (uploaded→zinc, processing→amber pulse, extracted→blue, approved→green,
   published→green solid, manual_queue→red, failed→red).
3. Review workbench: sticky header with progress (reviewed/total), confidence filter
   chips, keyboard nav, item row ↔ PDF page sync both ways.
4. Public tender page: document guide (from `document_intel` summaries), LV tree with
   search box, "For agents" block (MCP URL, JSON sample, OpenAPI).
5. Project cards: pipeline progress bar (uploaded→extracted→reviewed→published),
   item counts, deadline chip.

**Decision needed:** pick a direction (or the B+C+A mix) — then it becomes a
`docs/design-system.md` and gets implemented.
