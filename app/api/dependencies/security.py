from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_auth = HTTPBearer(auto_error=False)


def _validate_api_key(candidate: str | None) -> None:
    expected = settings.api_key
    if not expected:
        return
    if candidate and secrets.compare_digest(candidate, expected):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_api_key(
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_auth),
) -> None:
    bearer_token = bearer.credentials if bearer else None
    _validate_api_key(api_key or bearer_token)


def require_thumbnail_api_key(
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_auth),
) -> None:
    if not settings.PROTECT_THUMBNAILS_WITH_API_KEY:
        return
    bearer_token = bearer.credentials if bearer else None
    _validate_api_key(api_key or bearer_token)
