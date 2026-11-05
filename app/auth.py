from fastapi import HTTPException, Request

from app import config

# Tools that call OpenRouter / Gemini (or TTS that must translate first).
LLM_TOOL_IDS = frozenset({
    "summarize",
    "translate",
    "generate_document",
    "stt",
    "video_translate",
    "audio_translate",
    "youtube_summarize",
    "youtube_translate",
})


def _auth0_domain() -> str:
    return config.AUTH0_DOMAIN.replace("https://", "").rstrip("/")


def decode_auth0_bearer(token: str) -> dict:
    """Validate an Auth0 access token (user login or M2M client-credentials)."""
    if not config.AUTH0_DOMAIN or not config.AUTH0_AUDIENCE:
        raise HTTPException(status_code=500, detail="Auth0 is required but not configured")
    import jwt
    from jwt import PyJWKClient

    domain = _auth0_domain()
    jwks = PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.AUTH0_AUDIENCE,
            issuer=f"https://{domain}/",
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return token or None


def try_auth0_claims(request: Request) -> dict | None:
    """Return Auth0 claims when a Bearer token is present and valid.

    No Authorization header → None (caller may treat as anonymous).
    Invalid / missing Auth0 config with a Bearer present → 401/500.
    """
    token = bearer_token(request)
    if not token:
        return None
    return decode_auth0_bearer(token)


def check_auth(request: Request) -> None:
    """Validate Bearer JWT when AUTH_REQUIRED is on. No-op when auth is off."""
    if not config.AUTH_REQUIRED:
        return
    if not config.AUTH0_DOMAIN or not config.AUTH0_AUDIENCE:
        raise HTTPException(status_code=500, detail="Auth0 is required but not configured")
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required")
    decode_auth0_bearer(token)


def tool_requires_auth(tool_id: str, options: dict | None = None) -> bool:
    """Whether this tool run needs a signed-in user (LLM / paid AI path)."""
    if tool_id in LLM_TOOL_IDS:
        return True
    if tool_id != "tts":
        return False
    options = options or {}
    text = str(options.get("text") or "")
    language = str(options.get("language") or "en")
    try:
        from app.tools import media as media_tool

        lang = language.strip().lower() or "en"
        if lang.startswith("zh") and lang not in {"yue", "zh-hk", "zh_hk"}:
            lang = "zh"
        if lang in {"yue", "zh-hk", "zh_hk"}:
            lang = "yue"
        detected = media_tool._detect_tts_lang(text, "en")
        return detected != lang
    except Exception:
        return True
