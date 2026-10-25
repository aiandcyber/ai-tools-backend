import httpx
from fastapi import HTTPException, Request

from app import config

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("cf-connecting-ip") or "").strip()
    if forwarded:
        return forwarded
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


def verify_turnstile(request: Request, token: str) -> None:
    """Fail closed when TURNSTILE_SECRET is set. Skip when it is not configured."""
    if not config.TURNSTILE_SECRET:
        return
    if not config.TURNSTILE_HOSTNAMES:
        raise HTTPException(status_code=403, detail="Could not verify you are human. Try again.")
    text = (token or "").strip()
    if not text or len(text) > 2048:
        raise HTTPException(status_code=403, detail="Could not verify you are human. Try again.")
    try:
        response = httpx.post(
            _VERIFY_URL,
            data={
                "secret": config.TURNSTILE_SECRET,
                "response": text,
                "remoteip": _client_ip(request),
            },
            timeout=10,
        )
        result = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=403,
            detail="Could not verify you are human. Try again.",
        ) from exc
    if not response.is_success or result.get("success") is not True:
        raise HTTPException(status_code=403, detail="Could not verify you are human. Try again.")
    # Cloudflare dummy keys return hostname "example.com" and no action.
    testing = bool((result.get("metadata") or {}).get("result_with_testing_key"))
    if testing:
        return
    action = str(result.get("action") or "")
    hostname = str(result.get("hostname") or "")
    if action != config.TURNSTILE_ACTION or hostname not in config.TURNSTILE_HOSTNAMES:
        raise HTTPException(status_code=403, detail="Could not verify you are human. Try again.")
