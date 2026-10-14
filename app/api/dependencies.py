"""FastAPI dependencies for authentication, rate limiting, and shared state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.services.security import RateLimiter, verify_bearer_token

# ── Module-level rate limiter (created once, shared across requests) ──

_rate_limiter: RateLimiter | None = None


def _get_rate_limiter(settings: Settings | None = None) -> RateLimiter:
    """Get or create the global rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        if settings is None:
            settings = get_settings()
        _rate_limiter = RateLimiter(
            max_requests=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None


# ── Authentication dependency ──


async def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate Bearer token authentication.

    Returns the validated token on success.
    Raises HTTP 401 if missing or invalid.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required", "detail": "Missing Authorization header", "code": "AUTH_MISSING"},
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "detail": "Authorization header must be 'Bearer <token>'", "code": "AUTH_INVALID_FORMAT"},
        )

    token = parts[1]
    if not verify_bearer_token(token, settings.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "detail": "Invalid API token", "code": "AUTH_INVALID_TOKEN"},
        )

    return token


# ── Rate limiting dependency ──


async def check_rate_limit(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Check rate limit for the client.

    Uses client IP as the rate limit key.
    Raises HTTP 429 if rate limit exceeded.
    """
    limiter = _get_rate_limiter(settings)
    client_ip = request.client.host if request.client else "unknown"

    if not limiter.check(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "detail": f"Rate limit of {settings.RATE_LIMIT_REQUESTS} requests per {settings.RATE_LIMIT_WINDOW_SECONDS}s exceeded",
                "code": "RATE_LIMITED",
            },
        )


# ── Composite dependency for authenticated + rate-limited endpoints ──


async def require_auth_and_rate_limit(
    request: Request,
    token: str = Depends(require_auth),
    _: None = Depends(check_rate_limit),
) -> str:
    """Combined dependency: authenticate and check rate limit.

    Returns the validated token.
    """
    return token
