import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip()
OPENROUTER_STT_MODEL = os.getenv("OPENROUTER_STT_MODEL", "openai/whisper-1").strip()

# LLM routing: auto | openrouter | gemini
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower() or "auto"
# When primary fails, retry once with Gemini if a key is set
LLM_FALLBACK_GEMINI = os.getenv("LLM_FALLBACK_GEMINI", "true").strip().lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
).rstrip("/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").strip().lower() == "true"
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").strip()
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "").strip()

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5174,https://tools.ai-forall.org",
    ).split(",")
    if origin.strip()
]

JOB_ROOT = Path(os.getenv("JOB_ROOT", "/tmp/ai-tools-jobs"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(80 * 1024 * 1024)))
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
SEARCH_DEFAULT_REGION = os.getenv("SEARCH_DEFAULT_REGION", "SG").strip().upper() or "SG"

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "contact@ai-forall.org").strip() or "contact@ai-forall.org"
FEEDBACK_TO = os.getenv("FEEDBACK_TO", "contact@ai-forall.org").strip() or "contact@ai-forall.org"
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
CF_EMAIL_API_TOKEN = os.getenv("CF_EMAIL_API_TOKEN", "").strip()
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "").strip()
TURNSTILE_HOSTNAMES = {
    host.strip()
    for host in os.getenv("TURNSTILE_HOSTNAMES", "").split(",")
    if host.strip()
}
TURNSTILE_ACTION = os.getenv("TURNSTILE_ACTION", "contact").strip() or "contact"
