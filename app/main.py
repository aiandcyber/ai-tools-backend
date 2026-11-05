import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app import config
from app.agent import CHAT_DOWNLOADS, CHAT_FILES, build_orchestrator, resolve_llm_provider
from app.auth import bearer_token, check_auth, try_auth0_claims, tool_requires_auth
from app.catalog import BY_ID, CATEGORIES, TOOLS
from app.mail import send_feedback
from app.rate_limit import enforce_rate_limit
from app.turnstile import client_ip, verify_turnstile
from app.runner import export_text, run_tool
from app import jobs, upload_security
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
        "search_gate": {
            "casual_turnstile": bool(config.TURNSTILE_SECRET),
            "casual_rate_limit": config.SEARCH_CASUAL_RATE_LIMIT,
            "casual_rate_window_sec": config.SEARCH_CASUAL_RATE_WINDOW_SEC,
            "app_auth0_bearer": bool(config.AUTH0_DOMAIN and config.AUTH0_AUDIENCE),
        },
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
    tool = BY_ID.get(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown tool")
    options, saved = await _read_form(
        request,
        accept=tool.accept,
        max_bytes=upload_security.resolved_max_upload_bytes(
            tool.id, tool.category, tool.max_upload_bytes
        ),
        category=tool.category,
    )
    if tool_requires_auth(tool_id, options):
        check_auth(request)
    client_job = str(options.pop("job_id", "") or "").strip() or None
    job = jobs.create_job(tool_id, client_job)
    task = asyncio.create_task(asyncio.to_thread(run_tool, tool_id, saved, options, job.cancel))
    outcome = None
    try:
        while not task.done():
            if await request.is_disconnected() or job.cancel.is_set():
                job.cancel.set()
            await asyncio.sleep(0.15)
        try:
            outcome = task.result()
        except RuntimeError as exc:
            if "Cancelled" in str(exc) or job.cancel.is_set():
                raise HTTPException(status_code=499, detail="Cancelled") from exc
            raise
        if job.cancel.is_set():
            raise HTTPException(status_code=499, detail="Cancelled")
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown tool") from None
    except HTTPException:
        raise
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
        if job.cancel.is_set() or "Cancelled" in str(exc):
            raise HTTPException(status_code=499, detail="Cancelled") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        jobs.finish_job(job.id)
        for path in saved:
            upload_security.delete_quietly(path)
    return {
        "message": outcome.message,
        "downloads": [publish(item) for item in outcome.files],
        "results": outcome.results,
        "meta": {**outcome.meta, "job_id": job.id},
        "job_id": job.id,
    }


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_tool_job(job_id: str):
    if not jobs.cancel_job(job_id):
        # Still OK — client abort alone cancels via disconnect.
        return {"ok": True, "job_id": job_id, "cancelled": True}
    return {"ok": True, "job_id": job_id, "cancelled": True}


@app.post("/api/upload/basic-scan")
async def upload_basic_scan(request: Request):
    """Basic type/size/virus gate for the shared upload module (no long-term store)."""
    form = await request.form()
    accept = str(form.get("accept") or "*/*")
    category = str(form.get("category") or "ai")
    tool_id = str(form.get("tool_id") or "")
    try:
        max_bytes = int(form.get("max_bytes") or 0)
    except ValueError:
        max_bytes = 0
    if max_bytes <= 0:
        max_bytes = upload_security.resolved_max_upload_bytes(tool_id, category, 0)
    upload = form.get("file")
    if not upload or not getattr(upload, "filename", None):
        raise HTTPException(status_code=400, detail="Need a file")
    data = await upload.read()
    result = upload_security.gate_upload(
        filename=str(upload.filename),
        content_type=str(getattr(upload, "content_type", "") or ""),
        data=data,
        accept=accept,
        max_bytes=max_bytes,
    )
    if not result.ok:
        status = 413 if result.stage == "size" else 400
        raise HTTPException(status_code=status, detail=result.detail or "Upload rejected")
    # Optional ClamAV after a temp quarantine write.
    try:
        path = upload_security.write_quarantine(data, str(upload.filename))
        upload_security.delete_quietly(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "stage": "ready",
        "size": len(data),
        "max_bytes": max_bytes,
        "labels": result.labels or [],
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


def _gate_search_access(request: Request, body: dict) -> str:
    """Option B: anonymous = Turnstile + rate limit. Option C: Auth0 Bearer (user or M2M)."""
    if bearer_token(request):
        try_auth0_claims(request)  # invalid Bearer must not fall through to casual
        return "auth0"
    enforce_rate_limit(
        f"search:{client_ip(request)}",
        limit=config.SEARCH_CASUAL_RATE_LIMIT,
        window_sec=config.SEARCH_CASUAL_RATE_WINDOW_SEC,
    )
    token = str(
        body.get("cf-turnstile-response")
        or body.get("turnstile_token")
        or ""
    ).strip()
    verify_turnstile(request, token, expected_action=config.SEARCH_TURNSTILE_ACTION)
    return "casual"


@app.post("/api/search")
async def search_api(request: Request):
    """JSON search API for Tools UI and realtime-ai (news / recommendations / requests)."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    _gate_search_access(request, body)
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
    _gate_search_access(request, body)
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/search/people/reject", body)


@app.post("/api/biometrics/enroll")
async def biometrics_enroll_proxy(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    _gate_search_access(request, body)
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/biometrics/enroll", body)


@app.post("/api/biometrics/search")
async def biometrics_search_proxy(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    _gate_search_access(request, body)
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/biometrics/search", body)


@app.post("/api/vision/search")
async def vision_search_proxy(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    _gate_search_access(request, body)
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/vision/search", body)


@app.post("/api/counsel")
async def counsel_proxy(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/counsel", body)


@app.post("/api/knowledge/ingest")
async def knowledge_ingest_proxy(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/knowledge/ingest", body)


@app.post("/api/knowledge/bootstrap")
def knowledge_bootstrap_proxy():
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_post("/api/knowledge/bootstrap", {})


@app.get("/api/knowledge/sources")
def knowledge_sources_proxy():
    if not config.SEARCH_API_URL:
        raise HTTPException(status_code=503, detail="Search API is not configured")
    return _search_api_get("/api/knowledge/sources")


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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_delta(event) -> str:
    if isinstance(event, str):
        return event
    if not isinstance(event, dict):
        return ""
    if event.get("current_tool_use") and not event.get("data"):
        return ""
    data = event.get("data")
    if isinstance(data, str) and data:
        return data
    text = event.get("text")
    if isinstance(text, str) and text:
        return text
    return ""


def _wants_chat_stream(request: Request, options: dict) -> bool:
    flag = str(options.get("stream") or "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    accept = request.headers.get("accept", "")
    return "text/event-stream" in accept


async def _iter_agent_text(prompt: str, provider: str):
    agent = _agent(provider)
    async for event in agent.stream_async(prompt):
        piece = _event_delta(event)
        if piece:
            yield piece


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
    names = ", ".join(path.name for path in saved) or "none"
    prompt = f"User language code: {language}.\nAttached files: {names}.\n\n{message}"
    stream = _wants_chat_stream(request, options)

    def _run(provider: str):
        return _agent(provider)(prompt)

    async def _generate(provider: str):
        got = False
        async for piece in _iter_agent_text(prompt, provider):
            got = True
            yield piece
        if not got:
            result = await asyncio.to_thread(_run, provider)
            text = str(result or "")
            if text:
                yield text

    if not stream:
        provider_used = None
        result = None
        file_token = CHAT_FILES.set(saved)
        download_token = CHAT_DOWNLOADS.set([])
        try:
            try:
                provider_used = resolve_llm_provider()
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

    # ContextVars must be set/reset inside the streaming task. Tokens created in the
    # request handler cannot be reset from Starlette's stream task group.
    async def events():
        provider_used = None
        file_token = CHAT_FILES.set(saved)
        download_token = CHAT_DOWNLOADS.set([])
        try:
            try:
                provider_used = resolve_llm_provider()
                async for piece in _generate(provider_used):
                    yield _sse({"type": "delta", "text": piece})
            except Exception as primary_exc:
                can_fallback = (
                    config.LLM_FALLBACK_GEMINI
                    and config.GEMINI_API_KEY
                    and provider_used != "gemini"
                )
                if not can_fallback:
                    raise
                provider_used = "gemini"
                _ = primary_exc
                async for piece in _generate("gemini"):
                    yield _sse({"type": "delta", "text": piece})
            downloads = list(CHAT_DOWNLOADS.get())
            yield _sse({"type": "done", "downloads": downloads, "llm_provider": provider_used})
        except Exception as exc:
            yield _sse({"type": "error", "detail": str(exc)})
        finally:
            CHAT_FILES.reset(file_token)
            CHAT_DOWNLOADS.reset(download_token)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/stt")
async def stt_api(request: Request, _: None = Depends(check_auth)):
    _options, saved = await _read_form(request)
    if not saved:
        raise HTTPException(status_code=400, detail="Could not hear audio. Try Voice again.")
    from app.tools import media as media_tool

    try:
        text = await asyncio.to_thread(media_tool.speech_to_text, saved[0])
    except Exception as exc:
        detail = str(exc)
        lower = detail.lower()
        if any(token in lower for token in ("traceback", "openrouter", "api key", "httpx", "status code", "{")):
            detail = "Could not hear that. Try Voice again."
        raise HTTPException(status_code=502, detail=detail) from exc
    return {"text": text}


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
    verify_turnstile(request, token, expected_action="contact")
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
    from app.tools import media as media_tool

    text = media_tool.speakable_text(str(options.get("text") or ""))
    language = str(options.get("language") or "en").strip() or "en"
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    # Keep replies snappy for speak-aloud
    if len(text) > 4000:
        text = text[:4000] + "…"

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


async def _read_form(
    request: Request,
    *,
    accept: str = "*/*",
    max_bytes: int | None = None,
    category: str = "ai",
) -> tuple[dict, list[Path]]:
    form = await request.form()
    options: dict[str, str] = {}
    uploads = []
    for key, value in form.multi_items():
        if getattr(value, "filename", None):
            uploads.append(value)
        else:
            options[key] = str(value)
    limit = max_bytes if max_bytes and max_bytes > 0 else upload_security.resolved_max_upload_bytes(
        "", category, 0
    )
    return options, await _save_uploads(uploads, accept=accept, max_bytes=limit)


async def _save_uploads(files, *, accept: str = "*/*", max_bytes: int) -> list[Path]:
    saved: list[Path] = []
    for upload in files:
        data = await upload.read()
        filename = str(getattr(upload, "filename", None) or "upload.bin")
        content_type = str(getattr(upload, "content_type", None) or "")
        result = upload_security.gate_upload(
            filename=filename,
            content_type=content_type,
            data=data,
            accept=accept,
            max_bytes=max_bytes,
        )
        if not result.ok:
            status = 413 if result.stage == "size" else 400
            raise HTTPException(status_code=status, detail=result.detail or "Upload rejected")
        try:
            dest = upload_security.write_quarantine(data, filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        saved.append(dest)
    return saved
