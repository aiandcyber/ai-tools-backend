from fastapi import HTTPException, Request

from app import config


def check_auth(request: Request) -> None:
    if not config.AUTH_REQUIRED:
        return
    if not config.AUTH0_DOMAIN or not config.AUTH0_AUDIENCE:
        raise HTTPException(status_code=500, detail="Auth0 is required but not configured")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    token = header.split(" ", 1)[1]
    import jwt
    from jwt import PyJWKClient

    domain = config.AUTH0_DOMAIN.replace("https://", "").rstrip("/")
    jwks = PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.AUTH0_AUDIENCE,
            issuer=f"https://{domain}/",
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
