# AI Tools — Backend

FastAPI + Amazon Strands (multi-agent, Skills, Hooks, Guardrails, MCP) for **AI-for All Tools**.

- **GitHub:** https://github.com/aiandcyber/ai-tools-backend  
- **Production host:** Docker container from this `Dockerfile` on your API host, public via Cloudflare Tunnel (e.g. `https://api.tools.ai-forall.org`)  
- **Frontend:** https://github.com/aiandcyber/ai-tools-frontend → Cloudflare Pages  

## Layout

```
app/           # FastAPI application
skills/        # Strands Agent Skills (SKILL.md)
mcp_servers/   # Local MCP server used by the Strands orchestrator
searxng/       # Recommended SearXNG settings (shared service — not run inside this image)
Dockerfile
requirements.txt
```

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set OPENROUTER_API_KEY, SEARXNG_URL, etc.
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health: `GET /api/health`  
Strands demo status: `GET /api/demo/strands`

## Docker

Build context = **this repo root** (where `Dockerfile` lives).

```bash
docker build -t ai-tools-backend .
docker run --rm -p 8000:8000 --env-file .env ai-tools-backend
```

### Required / important env vars

| Variable | Notes |
|---|---|
| `OPENROUTER_API_KEY` | Assistant + AI tools |
| `CORS_ORIGINS` | Must include `https://tools.ai-forall.org` |
| `SEARXNG_URL` | Shared SearXNG base URL (not localhost in prod) |
| `SEARCH_DEFAULT_REGION` | e.g. `SG` (pilot ranking table; product regions are HK/CN/IN/US/OTHER) |
| `AUTH_REQUIRED` | `false` until Auth0 is enforced for LLM tools |
| `AUTH0_DOMAIN` / `AUTH0_AUDIENCE` | Auth0 tenant; same audience for user JWTs and M2M app tokens |
| `TURNSTILE_SECRET` / `TURNSTILE_HOSTNAMES` | Casual search + contact form bot check |
| `TURNSTILE_ACTIONS` | e.g. `contact,search` |
| `SEARCH_TURNSTILE_ACTION` | `search` (browser anonymous `/api/search`) |
| `SEARCH_CASUAL_RATE_LIMIT` | Max anonymous searches per IP per window (default `30`) |
| `SEARCH_CASUAL_RATE_WINDOW_SEC` | Window seconds (default `60`) |
| `JOB_ROOT` | Writable path in the container (default `/tmp/ai-tools-jobs`) |
| `PORT` | Container listens on `8000` (see `Dockerfile` `EXPOSE`) |

### Search access (Option B + C)

`POST /api/search` (and people reject) is gated at this Tools API edge:

| Caller | How |
|---|---|
| **Casual browser** (no Sign in) | Cloudflare Turnstile token in JSON (`cf-turnstile-response`, action `search`) + per-IP rate limit. No static API key in the SPA. |
| **Apps / backends** (Senior, Family, etc.) | `Authorization: Bearer <Auth0 access token>` — user login JWT **or** Auth0 **Machine-to-Machine** client-credentials token for audience `AUTH0_AUDIENCE`. Client id/secret live only in server env / host secret store, never in git or the APK. |

Do **not** expose the slim Search service (`SEARCH_API_URL`) on the public internet; keep it internal and proxy through this API.

### Health check

Path: `/api/health` · Port: `8000`

### SearXNG (shared)

This image does **not** run SearXNG. Deploy SearXNG once (shared), mount/use settings from `searxng/settings.yml` as a starting point, and set `SEARXNG_URL` on this service.

## First push to GitHub (run yourself)

From this folder (`ai-tools/backend`), after the empty repo exists:

```bash
git init
git add .
git commit -m "Initial AI Tools backend"
git branch -M main
git remote add origin https://github.com/aiandcyber/ai-tools-backend.git
git push -u origin main
```

Do **not** commit `.env`, `.venv/`, or secrets.
