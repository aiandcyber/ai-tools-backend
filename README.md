# AI Tools — Backend

FastAPI + Amazon Strands (multi-agent, Skills, Hooks, Guardrails, MCP) for **AI-for All Tools**.

- **GitHub:** https://github.com/aiandcyber/ai-tools-backend  
- **Production host (planned):** AWS Fargate (container from this `Dockerfile`)  
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

## Docker / Fargate

Build context = **this repo root** (where `Dockerfile` lives).

```bash
docker build -t ai-tools-backend .
docker run --rm -p 8000:8000 --env-file .env ai-tools-backend
```

### Required / important env vars (task definition secrets)

| Variable | Notes |
|---|---|
| `OPENROUTER_API_KEY` | Assistant + AI tools |
| `CORS_ORIGINS` | Must include `https://tools.ai-forall.org` |
| `SEARXNG_URL` | Shared SearXNG base URL (not localhost in prod) |
| `SEARCH_DEFAULT_REGION` | e.g. `SG` |
| `AUTH_REQUIRED` | `false` until Auth0 is enforced |
| `AUTH0_DOMAIN` / `AUTH0_AUDIENCE` | When auth is enabled |
| `JOB_ROOT` | Writable path in the task (default `/tmp/ai-tools-jobs`) |
| `PORT` | Container listens on `8000` (see `Dockerfile` `EXPOSE`) |

### ALB health check

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
