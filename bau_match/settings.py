import os
from pathlib import Path

from dotenv import load_dotenv

# override=True: the host's .env beats any inherited environment (rambo spec §2.1)
load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me-in-production")

DEBUG = os.getenv("DEBUG", "True") == "True"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    # jazzy-tabler must come before django.contrib.admin
    "jazzy_tabler",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # third-party
    "allauth",
    "allauth.account",
    "django_rq",
    # local
    "accounts",
    "core",
    "projects",
    "extraction",
    "bidding",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "bau_match.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bau_match.wsgi.application"
ASGI_APPLICATION = "bau_match.asgi.application"

# Database — POSTGRES_* per rambo hosting contract; SQLite fallback for local dev
if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", ""),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.getenv("STATIC_ROOT") or (BASE_DIR / "staticfiles")
MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT") or (BASE_DIR / "media")

# Private uploads (tender PDFs) — served through Django, never via the web server
PRIVATE_ROOT = os.getenv("PRIVATE_ROOT") or (BASE_DIR / "private")

# HTTPS behind Nginx (rambo hosting contract)
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")
] + [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# django-allauth
AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
]
SITE_ID = 1

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "optional")
ACCOUNT_DEFAULT_HTTP_PROTOCOL = os.getenv("ACCOUNT_HTTP_PROTOCOL", "http")

LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"

# Email — console for dev, configure via env vars for production
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "True") == "True"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@azmy.raenterprises.de")

# Redis / RQ (rambo host provides REDIS_URL; extraction falls back to sync in dev)
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    RQ_QUEUES = {"default": {"URL": REDIS_URL, "DEFAULT_TIMEOUT": 3600}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    RQ_QUEUES = {"default": {"URL": "redis://localhost:6379/0", "DEFAULT_TIMEOUT": 3600}}

RQ_ENABLED = bool(REDIS_URL) and os.getenv("RQ_ENABLED", "True") == "True"

# OpenRouter — LLM extraction/structuring/judge/OCR.
# Per-task routing: free-tier defaults; override any task via env (docs/phase-2-design.md).
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL_METADATA = os.getenv(
    "OPENROUTER_MODEL_METADATA", "qwen/qwen3.8-27b:free,google/gemini-2.5-flash"
)
OPENROUTER_MODEL_STRUCTURE = os.getenv(
    "OPENROUTER_MODEL_STRUCTURE", "qwen/qwen3.8-27b:free,google/gemini-2.5-flash"
)
OPENROUTER_MODEL_OCR = os.getenv(
    "OPENROUTER_MODEL_OCR", "google/gemma-4-31b-it:free,google/gemini-2.5-flash"
)
OPENROUTER_MODEL_JUDGE = os.getenv(
    "OPENROUTER_MODEL_JUDGE", "qwen/qwen3.8-27b:free,google/gemini-2.5-flash"
)
# vision OCR: max pages per document (scans beyond this go to manual queue)
OPENROUTER_OCR_MAX_PAGES = int(os.getenv("OPENROUTER_OCR_MAX_PAGES", "80"))

LOGIN_URL = "/accounts/login/"
