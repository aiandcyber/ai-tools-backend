import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import config
from app.agent import CHAT_DOWNLOADS, CHAT_FILES, build_orchestrator
from app.auth import check_auth
from app.catalog import CATEGORIES, TOOLS
from app.runner import run_tool
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


def _agent():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "auth_required": config.AUTH_REQUIRED,
        "openrouter": bool(config.OPENROUTER_API_KEY),
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
async def execute_tool(tool_id: str, request: Request, _: None = Depends(check_auth)):
    options, saved = await _read_form(request)
    try:
        outcome = run_tool(tool_id, saved, options)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown tool") from None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": outcome.message,
        "downloads": [publish(item) for item in outcome.files],
        "results": outcome.results,
        "meta": outcome.meta,
    }


@app.post("/api/search")
async def search_api(request: Request, _: None = Depends(check_auth)):
    """JSON search API for Tools UI and realtime-ai (news / recommendations / requests)."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
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


@app.get("/api/search/regions")
def search_regions() -> dict:
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
    if not config.OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="Set OPENROUTER_API_KEY to use the assistant")
    options, saved = await _read_form(request)
    message = str(options.get("message", ""))
    language = str(options.get("language", "en"))
    file_token = CHAT_FILES.set(saved)
    download_token = CHAT_DOWNLOADS.set([])
    try:
        names = ", ".join(path.name for path in saved) or "none"
        prompt = f"User language code: {language}.\nAttached files: {names}.\n\n{message}"
        result = _agent()(prompt)
        downloads = list(CHAT_DOWNLOADS.get())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        CHAT_FILES.reset(file_token)
        CHAT_DOWNLOADS.reset(download_token)
    return {"reply": str(result), "downloads": downloads}


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
