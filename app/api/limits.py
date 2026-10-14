"""Limits endpoint — returns current server configuration limits."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_auth
from app.config import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["limits"])


@router.get("/limits", status_code=status.HTTP_200_OK)
async def get_limits(
    _token: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return current server configuration limits.

    Useful for clients to know constraints before submitting jobs.
    """
    return {
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "max_duration_seconds": settings.MAX_DURATION_SECONDS,
        "max_playlist_length": settings.MAX_PLAYLIST_LENGTH,
        "max_concurrent_jobs": settings.MAX_CONCURRENT_JOBS,
        "max_queue_size": settings.MAX_QUEUE_SIZE,
        "supported_formats": settings.SUPPORTED_FORMATS,
        "supported_qualities": settings.SUPPORTED_QUALITIES,
        "job_timeout_seconds": settings.JOB_TIMEOUT_SECONDS,
        "artifact_ttl_seconds": settings.ARTIFACT_TTL_SECONDS,
        "rate_limit_requests": settings.RATE_LIMIT_REQUESTS,
        "rate_limit_window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
    }
