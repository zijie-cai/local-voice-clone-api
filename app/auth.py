from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_auth", "message": "Missing Authorization header"},
        )

    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_auth", "message": "Invalid Authorization header format"},
        ) from exc

    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_auth_scheme", "message": "Use Bearer token auth"},
        )

    if not secrets.compare_digest(token.strip(), settings.auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Token rejected"},
        )
