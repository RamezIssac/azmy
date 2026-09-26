# Deployment Plan — azmy.raenterprises.de via rambo

Status: **agreed baseline** (2026-09-26).

## Ground truth (verified against rambo's generated workspaces)

- Deploy is admin-driven in rambo: **HostedApplication** record → action
  *"Deploy selected applications using Ansible"* → workspace rendered under
  `rambo/var/hosting/<server>/` → `deploy.yml` runs roles: **django_app → daphne → ttyd**
  (+ nginx vhost per app). `redeploy.yml` exists for app-only redeploys.
- The host writes `.env` from `roles/django_app/templates/dotenv.j2` with **exactly**:
  `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `POSTGRES_DB/USER/PASSWORD/HOST/PORT`,
  `REDIS_URL`, `DJANGO_SETTINGS_MODULE`, `STATIC_ROOT`, `MEDIA_ROOT`, plus any
  `extra_env` keys (→ `OPENROUTER_API_KEY` goes there).
- Existing `raenterprises.de` apps (`rambo.`, `slick-demo.`) live on server **rasystem26**
  → azmy defaults to rasystem26.
- Deploy does: git clone/update → uv venv + pip install → migrate → compilemessages →
  collectstatic → uWSGI vassal → **rqworker systemd unit** (when worker enabled) →
  daphne → nginx static/media alias.

## Contract compliance work in bau_match (I do this, no decision needed)

- [ ] Rename DB env reading → `POSTGRES_DB/USER/PASSWORD/HOST/PORT` (currently `DB_*`).
- [ ] `STATIC_ROOT` / `MEDIA_ROOT` from env (currently hardcoded `BASE_DIR/staticfiles`).
- [ ] `STATIC_URL = "/static/"`, `MEDIA_URL = "/media/"`.
- [ ] HTTPS: `CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`.
- [ ] `REDIS_URL` → `CACHES` + `RQ_QUEUES` (channels only if/when we add websockets).
- [ ] Add deps: `django-rq`, `redis`, `psycopg[binary]` (replace psycopg2-binary),
      PDF stack (pypdf/pdfplumber), httpx (OpenRouter), GAEB X83 XML parsing.
- [ ] Ensure `wsgi.py`/`asgi.py` importable as registered modules.
- [ ] `.env` in `.gitignore`; `.env.example` updated to POSTGRES_* names.
- [ ] v1 simplifications: no channels/daphne dependency (extraction progress via htmx
      polling); allauth email verification → `optional` (internal tool, users created
      by us via CLI); real SMTP later via `extra_env`.

## The automatized path to production

```
me: build → test locally (sqlite + fakeredis) → lint → push to origin/<branch>
you: (once) create HostedApplication in rambo admin from my field sheet
     (once) add deploy key to repo host + DNS A record
you/CI: click "Deploy selected applications" in rambo  →  azmy.raenterprises.de live
```

## Blockers — RESOLVED (2026-09-26)

1. **Git remote** — `git@github.com:RamezIssac/azmy.git` ✅
2. **Server** — rasystem26 ✅ confirmed
3. **DNS** — azmy.raenterprises.de → rasystem26 ✅ done
4. **HostedApplication record** — shell access granted; agent creates the record in the
   rambo instance directly ✅
5. **OpenRouter key** — available ✅ (stored in the `knowledge_consolidator` app's config;
   reuse it, put into rambo `extra_env` as `OPENROUTER_API_KEY`)

## Acceptance criteria — "first stable run"

1. `https://azmy.raenterprises.de` serves the staff login over valid TLS.
2. Staff uploads `rockenbauarbeiten.pdf` → extraction runs via RQ → LV tree in review UI.
3. Human approves → public read link + `GET /api/v1/projects/<id>/` returns the LV tree.
4. GAEB X83 import accepts a sample file into the same tree.
5. Redeploy (push → rambo deploy) is green end-to-end.
