import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import config
from app.agent import CHAT_DOWNLOADS, CHAT_FILES, build_orchestrator, resolve_llm_provider
from app.auth import check_auth, tool_requires_auth
from app.catalog import CATEGORIES, TOOLS
from app.mail import send_feedback
from app.turnstile import verify_turnstile
from app.runner import export_text, run_tool
from app.workspace import publish, resolve_download

app = FastAPI(title="AI-for All Tools")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_orchestrator = None
_orchestrator_provider: str | None = None


def _has_llm_key() -> bool:
    return bool(config.OPENROUTER_API_KEY or config.GEMINI_API_KEY)


def _agent(provider: str | None = None):
    global _orchestrator, _orchestrator_provider
    wanted = resolve_llm_provider(provider)
    if _orchestrator is None or _orchestrator_provider != wanted:
        _orchestrator = build_orchestrator(wanted)
        _orchestrator_provider = wanted
    return _orchestrator


@app.get("/api/health")
def health() -> dict:
    provider = None
    try:
        provider = resolve_llm_provider()
    except Exception:
        provider = None
    return {
        "status": "ok",
        "auth_required": config.AUTH_REQUIRED,
        "auth0_configured": bool(config.AUTH0_DOMAIN and config.AUTH0_AUDIENCE),
        "openrouter": bool(config.OPENROUTER_API_KEY),
        "gemini": bool(config.GEMINI_API_KEY),
        "llm_provider": provider,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "libreoffice": bool(shutil.which("soffice") or shutil.which("libreoffice")),
        "tesseract": bool(shutil.which("tesseract")),
        "strands": {
            "multi_agent": True,
            "skills": True,
            "hooks": True,
            "guardrails": True,
            "mcp": True,
        },
    }


@app.get("/api/demo/strands")
def demo_strands() -> dict:
    """Interview/demo endpoint: Skills, Hooks, Guardrails, MCP status + recent hook events."""
    from app.agent import strands_feature_status

    return strands_feature_status()


@app.get("/api/tools")
def list_tools() -> dict:
    return {
        "categories": [{"id": key, "title": title} for key, title in CATEGORIES],
        "tools": [item.public() for item in TOOLS],
    }


@app.post("/api/tools/{tool_id}")
async def execute_tool(tool_id: str, request: Request):
    options, saved = await _read_form(request)
    if tool_requires_auth(tool_id, options):
        check_auth(request)
    try:
        outcome = await asyncio.to_thread(run_tool, tool_id, saved, options)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown tool") from None
    except Exception as exc:
        if tool_id == "tts":
            logging.getLogger("uvicorn.error").exception(
                "tts tool failed chars=%s lang=%s",
                len(str(options.get("text") or "")),
                options.get("language"),
            )
        if tool_id in {"youtube_mp4", "youtube_mp3"}:
            from app.tools import media as media_tool

            raise HTTPException(status_code=400, detail=media_tool.youtube_public_error(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": outcome.message,
        "downloads": [publish(item) for item in outcome.files],
        "results": outcome.results,
        "meta": outcome.meta,
    }


@app.post("/api/export-text")
async def export_text_api(request: Request):
    options, _saved = await _read_form(request)
    text = str(options.get("text") or "")
    fmt = str(options.get("format") or "txt")
    try:
        outcome = export_text(text, fmt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": outcome.message,
        "downloads": [publish(item) for item in outcome.files],
    }


def _search_api_get(path: str):
    import httpx

    try:
        response = httpx.get(f"{config.SEARCH_API_URL}{path}", timeout=35.0)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search API unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text[:300])
    return response.json()


def _search_api_post(path: str, body: dict):
    import httpx

    try:
        response = httpx.post(f"{config.SEARCH_API_URL}{path}", json=body, timeout=60.0)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search API unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text[:300])
    return response.json()


@app.post("/api/search")
async def search_api(request: Request):
    """JSON search API for Tools UI and realtime-ai (news / recommendations / requests)."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    if config.SEARCH_API_URL:
        return _search_api_post("/api/search", body)
    # Local fallback only. Production sets SEARCH_API_URL to the Search API.
    from app.tools import search as search_tool

    try:
        payload = search_tool.web_search(
            query=str(body.get("query") or ""),
            mode=str(body.get("mode") or "auto"),
            region=str(body.get("region") or ""),
            language=str(body.get("language") or "en"),
            interests=str(body.get("interests") or ""),
            industry=str(body.get("industry") or ""),
            location=str(body.get("location") or ""),
            limit=int(body.get("limit") or 20),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return payload


@app.post("/api/search/people/reject")
async def search_people_reject(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/search/people/reject", body)


@app.get("/api/search/regions")
def search_regions() -> dict:
    if config.SEARCH_API_URL:
        return _search_api_get("/api/search/regions")
    from app.tools.search import REGION_PROFILES

    return {
        "default": config.SEARCH_DEFAULT_REGION,
        "regions": [
            {"code": code, "label": info["label"]}
            for code, info in REGION_PROFILES.items()
        ],
    }


@app.post("/api/chat")
async def chat(request: Request, _: None = Depends(check_auth)):
    if not _has_llm_key():
        raise HTTPException(
            status_code=503,
            detail="Set OPENROUTER_API_KEY or GEMINI_API_KEY to use the assistant",
        )
    options, saved = await _read_form(request)
    message = str(options.get("message", ""))
    language = str(options.get("language", "en"))
    file_token = CHAT_FILES.set(saved)
    download_token = CHAT_DOWNLOADS.set([])
    provider_used = None
    result = None
    try:
        names = ", ".join(path.name for path in saved) or "none"
        prompt = f"User language code: {language}.\nAttached files: {names}.\n\n{message}"

        def _run(provider: str):
            return _agent(provider)(prompt)

        try:
            provider_used = resolve_llm_provider()
            # Strands agent is sync; run off the event loop so one chat can't freeze the API
            result = await asyncio.to_thread(_run, provider_used)
        except Exception as primary_exc:
            can_fallback = (
                config.LLM_FALLBACK_GEMINI
                and config.GEMINI_API_KEY
                and provider_used != "gemini"
            )
            if not can_fallback:
                raise
            provider_used = "gemini"
            result = await asyncio.to_thread(_run, "gemini")
            _ = primary_exc
        downloads = list(CHAT_DOWNLOADS.get())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        CHAT_FILES.reset(file_token)
        CHAT_DOWNLOADS.reset(download_token)
    return {"reply": str(result), "downloads": downloads, "llm_provider": provider_used}


@app.post("/api/youtube/probe")
async def youtube_probe(request: Request):
    options, _saved = await _read_form(request)
    url = str(options.get("url") or "").strip()
    kind = str(options.get("kind") or "mp4").strip().lower()
    if kind not in ("mp4", "mp3"):
        kind = "mp4"
    from app.tools import media as media_tool

    try:
        payload = await asyncio.to_thread(media_tool.youtube_probe, url, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=media_tool.youtube_public_error(exc)) from exc
    return payload


@app.post("/api/feedback")
async def feedback(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid form") from exc
    email = str(payload.get("email") or "").strip()
    topic = str(payload.get("topic") or "contact").strip().lower()
    youtube_url = str(payload.get("youtube_url") or payload.get("youtube") or "").strip()
    message = str(payload.get("message") or "").strip()
    token = str(
        payload.get("cf-turnstile-response")
        or payload.get("turnstile_token")
        or ""
    ).strip()
    if not email or not message:
        raise HTTPException(status_code=400, detail="Email and message are required")
    verify_turnstile(request, token)
    try:
        await asyncio.to_thread(send_feedback, email, youtube_url, message, topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logging.getLogger("uvicorn.error").exception("feedback email failed")
        raise HTTPException(
            status_code=502,
            detail="Could not send email. Check the address or try later.",
        ) from None
    return {"ok": True}


@app.post("/api/tts")
async def tts(request: Request):
    """Speak agent replies with edge-tts (neural voices). Returns audio/mpeg."""
    options, _saved = await _read_form(request)
    text = str(options.get("text") or "").strip()
    language = str(options.get("language") or "en").strip() or "en"
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    # Keep replies snappy for speak-aloud
    if len(text) > 4000:
        text = text[:4000] + "…"
    from app.tools import media as media_tool

    work = config.JOB_ROOT / "tts" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    dest = work / "speech.mp3"
    try:
        await media_tool.text_to_speech_async(text, language, dest)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc
    return FileResponse(dest, media_type="audio/mpeg", filename="speech.mp3")


@app.get("/api/files/{token}/{name}")
def download(token: str, name: str):
    try:
        path = resolve_download(token, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    return FileResponse(path, filename=path.name)


async def _read_form(request: Request) -> tuple[dict, list[Path]]:
    form = await request.form()
    options: dict[str, str] = {}
    uploads = []
    for key, value in form.multi_items():
        if getattr(value, "filename", None):
            uploads.append(value)
        else:
            options[key] = str(value)
    return options, await _save_uploads(uploads)


async def _save_uploads(files) -> list[Path]:
    saved: list[Path] = []
    work = config.JOB_ROOT / "incoming"
    work.mkdir(parents=True, exist_ok=True)
    for upload in files:
        data = await upload.read()
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File is too large")
        dest = work / f"{uuid.uuid4().hex}-{Path(upload.filename).name}"
        dest.write_bytes(data)
        saved.append(dest)
    return saved
