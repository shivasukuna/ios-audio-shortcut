"""Job management endpoints.

POST   /api/v1/jobs            — Submit a new download job
GET    /api/v1/jobs/{job_id}   — Get job status
GET    /api/v1/jobs/{job_id}/file — Get download token or download file
DELETE /api/v1/jobs/{job_id}   — Cancel/delete a job
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.api.dependencies import require_auth, require_auth_and_rate_limit
from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.models.job import JobStatus
from app.schemas.jobs import (
    ErrorResponse,
    FileTokenResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from app.services.security import (
    generate_download_token,
    sanitize_filename,
    validate_download_token,
    validate_url,
)
from app.workers.worker import worker_manager

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
logger = get_logger(__name__)


def _get_mime_type(filename: str) -> str:
    """Return the MIME type for an audio file based on extension."""
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".opus": "audio/opus",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }
    return mime_map.get(ext, "application/octet-stream")


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def create_job(
    body: JobCreateRequest,
    request: Request,
    _token: str = Depends(require_auth_and_rate_limit),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Submit a new audio download job.

    Validates the URL, checks queue limits and disk space,
    creates the job, and enqueues it for processing.
    Returns HTTP 202 with job ID and status URL.
    """
    from app.services.job_service import create_job as svc_create_job
    from app.services.job_service import get_active_count, get_queue_depth

    url_str = str(body.url)

    # ── Validate URL (SSRF protection) ──
    is_valid, error_reason = validate_url(url_str, settings.ALLOWED_HOSTS)
    if not is_valid:
        logger.warning("URL validation failed", extra={"reason": error_reason})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_url", "detail": error_reason, "code": "URL_INVALID"},
        )

    # ── Check disk space ──
    try:
        output_path = Path(settings.OUTPUT_DIR)
        output_path.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(output_path)
        used_percent = (disk.used / disk.total) * 100
        if used_percent >= settings.DISK_REJECT_PERCENT:
            logger.error("Disk usage too high, rejecting job", extra={"used_percent": round(used_percent, 1)})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "disk_full", "detail": "Server storage is full. Try again later.", "code": "DISK_FULL"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Disk check failed", extra={"error": str(exc)})

    # ── Check queue limits ──
    queue_depth = await get_queue_depth(settings.DB_PATH)
    if queue_depth >= settings.MAX_QUEUE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "queue_full", "detail": f"Job queue is full ({queue_depth}/{settings.MAX_QUEUE_SIZE}). Try again later.", "code": "QUEUE_FULL"},
        )

    active_count = await get_active_count(settings.DB_PATH)
    if active_count >= settings.MAX_QUEUE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "queue_full", "detail": "Too many active jobs. Try again later.", "code": "QUEUE_FULL"},
        )

    # ── Compute URL hash and extract host ──
    from urllib.parse import urlparse

    parsed = urlparse(url_str)
    source_host = parsed.hostname or "unknown"
    url_hash = hashlib.sha256(url_str.encode()).hexdigest()

    # ── Create job (handles dedup internally) ──
    job = await svc_create_job(
        db_path=settings.DB_PATH,
        url_hash=url_hash,
        source_host=source_host,
        output_format=body.format.value,
        output_quality=body.quality.value,
        original_url=url_str,
        artifact_ttl=settings.ARTIFACT_TTL_SECONDS,
    )

    # ── Submit to worker (only if newly queued) ──
    if job.status == JobStatus.QUEUED.value:
        submitted = worker_manager.submit_job(job.id, url_str)
        if not submitted:
            logger.warning("Failed to submit job to worker pool", extra={"job_id": job.id})

    logger.info(
        "Job created",
        extra={"job_id": job.id, "source_host": source_host, "format": body.format.value},
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.id,
            "status": job.status,
            "status_url": f"/api/v1/jobs/{job.id}",
            "created_at": job.created_at,
        },
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_job_status(
    job_id: str,
    _token: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Get the current status of a job."""
    from app.services.job_service import get_job

    job = await get_job(settings.DB_PATH, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "detail": "Job not found", "code": "JOB_NOT_FOUND"},
        )

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "output_filename": job.output_filename,
        "output_size": job.output_size,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "expires_at": job.expires_at,
    }


@router.get(
    "/{job_id}/file",
    response_model=None,
    responses={
        200: {"content": {"audio/mpeg": {}}},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
    },
)
async def get_job_file(
    job_id: str,
    token: str | None = Query(default=None, description="Short-lived download token"),
    authorization: str | None = None,
    request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """Get the audio file for a completed job.

    Two modes:
    1. With Bearer auth (no ?token=) → returns a short-lived download token URL
    2. With ?token= query param → validates token and serves the binary file

    This two-step approach avoids putting Bearer tokens in URLs for binary downloads,
    which is important for iOS Shortcuts compatibility.
    """
    from app.services.job_service import get_job

    # ── Mode 2: Token-based binary download ──
    if token is not None:
        is_valid, token_job_id = validate_download_token(token, settings.hmac_secret)
        if not is_valid or token_job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_token", "detail": "Download token is invalid or expired", "code": "TOKEN_INVALID"},
            )

        job = await get_job(settings.DB_PATH, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "not_found", "detail": "Job not found", "code": "JOB_NOT_FOUND"},
            )

        if job.status != JobStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"error": "not_available", "detail": f"Job is {job.status}, file not available", "code": "FILE_NOT_AVAILABLE"},
            )

        # Resolve file path safely
        if not job.output_filename:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"error": "not_available", "detail": "Output file not found", "code": "FILE_MISSING"},
            )

        file_dir = Path(settings.OUTPUT_DIR) / job.id
        file_path = file_dir / job.output_filename

        # Prevent path traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(file_dir.resolve())):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "forbidden", "detail": "Access denied", "code": "PATH_TRAVERSAL"},
                )
        except (OSError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "detail": "Invalid file path", "code": "PATH_INVALID"},
            )

        if not file_path.exists():
            logger.error("Output file missing from disk", extra={"job_id": job_id, "path": str(file_path)})
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={"error": "not_available", "detail": "File has been cleaned up or is missing", "code": "FILE_MISSING"},
            )

        safe_filename = sanitize_filename(job.output_filename)
        mime_type = _get_mime_type(safe_filename)

        logger.info("Serving file download", extra={"job_id": job_id, "size": job.output_size})

        return FileResponse(
            path=file_path,
            media_type=mime_type,
            filename=safe_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Cache-Control": "no-store",
            },
        )

    # ── Mode 1: Generate download token (requires Bearer auth) ──
    # Extract and validate Bearer token from Authorization header
    auth_header = request.headers.get("authorization") if request else None
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required", "detail": "Provide Bearer token or download token", "code": "AUTH_MISSING"},
        )

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "detail": "Invalid Authorization header", "code": "AUTH_INVALID_FORMAT"},
        )

    from app.services.security import verify_bearer_token

    if not verify_bearer_token(parts[1], settings.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "detail": "Invalid API token", "code": "AUTH_INVALID_TOKEN"},
        )

    # Verify job exists and is completed
    job = await get_job(settings.DB_PATH, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "detail": "Job not found", "code": "JOB_NOT_FOUND"},
        )

    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "not_ready", "detail": f"Job is {job.status}, not ready for download", "code": "JOB_NOT_READY"},
        )

    # Generate short-lived download token
    download_token = generate_download_token(
        job_id=job_id,
        secret=settings.hmac_secret,
        ttl_seconds=settings.DOWNLOAD_TOKEN_TTL_SECONDS,
    )

    download_url = f"/api/v1/jobs/{job_id}/file?token={download_token}"

    return {
        "download_url": download_url,
        "expires_in": settings.DOWNLOAD_TOKEN_TTL_SECONDS,
    }


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def delete_job(
    job_id: str,
    _token: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Cancel a pending job or delete a completed job's artifacts."""
    from app.services.job_service import delete_job as svc_delete_job

    deleted = await svc_delete_job(settings.DB_PATH, job_id, settings.OUTPUT_DIR)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "detail": "Job not found", "code": "JOB_NOT_FOUND"},
        )

    logger.info("Job deleted", extra={"job_id": job_id})
    return {"job_id": job_id, "status": "cancelled", "detail": "Job cancelled and artifacts cleaned up"}


@router.get(
    "/download",
    response_class=FileResponse,
    response_model=None,
    summary="Direct audio download for simple iOS Shortcuts",
)
async def download_direct(
    url: str = Query(..., description="Media URL to download"),
    token: str = Query(default="", description="API Token (if not using Authorization header)"),
    format: str = Query(default="mp3", description="Audio format (mp3, aac, opus, m4a)"),
    quality: str = Query(default="192k", description="Audio quality (128k, 192k, 320k, best)"),
    request: Request = None,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Download and return audio file directly in a single request.

    Designed for lightweight iOS Shortcuts without polling logic.
    """
    import asyncio
    import uuid
    from app.services.downloader import DownloadException, download_audio
    from app.services.security import verify_bearer_token

    # 1. Authentication check (Header or Query token)
    auth_header = request.headers.get("Authorization", "") if request else ""
    provided_token = ""
    if auth_header.startswith("Bearer "):
        provided_token = auth_header[7:].strip()
    elif token:
        provided_token = token.strip()

    if not provided_token or not verify_bearer_token(provided_token, settings.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
        )

    # 2. URL validation
    is_valid, reason = validate_url(url, settings.ALLOWED_HOSTS)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    # 3. Format and Quality validation
    fmt = format.lower()
    qlt = quality.lower()
    if fmt not in settings.SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format '{format}' not supported. Allowed: {settings.SUPPORTED_FORMATS}",
        )
    if qlt not in settings.SUPPORTED_QUALITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quality '{quality}' not supported. Allowed: {settings.SUPPORTED_QUALITIES}",
        )

    # 4. Process download in background thread
    job_id = f"direct-{uuid.uuid4().hex[:10]}"
    try:
        result = await asyncio.to_thread(
            download_audio,
            job_id=job_id,
            url=url,
            output_format=fmt,
            output_quality=qlt,
            output_dir=settings.OUTPUT_DIR,
            temp_dir=settings.TEMP_DIR,
            max_filesize_mb=settings.MAX_FILE_SIZE_MB,
            max_duration_seconds=settings.MAX_DURATION_SECONDS,
        )
    except DownloadException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extraction failed: {exc.message}",
        )
    except Exception as exc:
        logger.exception("Direct download unexpected failure", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal download failure: {exc}",
        )

    filepath = Path(result["filepath"])
    filename = result["filename"]
    mime_type = _get_mime_type(filename)

    return FileResponse(
        path=str(filepath),
        media_type=mime_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
