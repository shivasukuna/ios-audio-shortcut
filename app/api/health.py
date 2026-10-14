"""Health check endpoints.

- /health/live   — Process is alive (no auth)
- /health/ready  — Dependencies initialized (no auth)
- /health/deep   — Full diagnostics (auth required)
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.dependencies import require_auth
from app.config import Settings, get_settings
from app.database import get_db
from app.services.audio_processor import verify_ffmpeg

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Liveness probe — confirms the API process responds."""
    return {"status": "alive", "timestamp": time.time()}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Readiness probe — verifies DB and worker pool are initialized."""
    checks: dict[str, bool] = {}

    # Check database connectivity
    try:
        async with get_db(settings.DB_PATH) as db:
            await db.execute("SELECT 1")
            checks["database"] = True
    except Exception:
        checks["database"] = False

    # Check worker pool
    try:
        from app.workers.worker import worker_manager
        checks["worker_pool"] = worker_manager.is_alive()
    except Exception:
        checks["worker_pool"] = False

    all_ready = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
            "timestamp": time.time(),
        },
    )


@router.get("/deep", status_code=status.HTTP_200_OK)
async def deep_health(
    _token: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Deep health diagnostics — requires authentication.

    Checks all dependencies and reports detailed status.
    """
    components: dict[str, dict] = {}

    # ── Database ──
    try:
        async with get_db(settings.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM jobs")
            row = await cursor.fetchone()
            total_jobs = row[0] if row else 0
            components["database"] = {"healthy": True, "total_jobs": total_jobs}
    except Exception as exc:
        components["database"] = {"healthy": False, "error": str(exc)}

    # ── FFmpeg / FFprobe ──
    try:
        ff_info = verify_ffmpeg()
        components["ffmpeg"] = {
            "healthy": ff_info.get("ffmpeg_available", False),
            "ffmpeg_version": ff_info.get("ffmpeg_version", "unknown"),
            "ffprobe_available": ff_info.get("ffprobe_available", False),
            "ffprobe_version": ff_info.get("ffprobe_version", "unknown"),
        }
    except Exception as exc:
        components["ffmpeg"] = {"healthy": False, "error": str(exc)}

    # ── yt-dlp ──
    try:
        import yt_dlp
        components["yt_dlp"] = {"healthy": True, "version": yt_dlp.version.__version__}
    except Exception as exc:
        components["yt_dlp"] = {"healthy": False, "error": str(exc)}

    # ── Worker pool ──
    try:
        from app.workers.worker import worker_manager
        heartbeat = worker_manager.get_heartbeat()
        heartbeat_age = time.time() - heartbeat if heartbeat else None
        components["worker"] = {
            "healthy": worker_manager.is_alive(),
            "active_jobs": worker_manager.active_job_count(),
            "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        }
    except Exception as exc:
        components["worker"] = {"healthy": False, "error": str(exc)}

    # ── Disk space ──
    try:
        output_path = Path(settings.OUTPUT_DIR)
        output_path.mkdir(parents=True, exist_ok=True)
        disk_usage = shutil.disk_usage(output_path)
        used_percent = round((disk_usage.used / disk_usage.total) * 100, 1)
        components["disk"] = {
            "healthy": used_percent < settings.DISK_REJECT_PERCENT,
            "used_percent": used_percent,
            "free_gb": round(disk_usage.free / (1024**3), 2),
            "total_gb": round(disk_usage.total / (1024**3), 2),
            "warning": used_percent >= settings.DISK_WARNING_PERCENT,
        }
    except Exception as exc:
        components["disk"] = {"healthy": False, "error": str(exc)}

    # ── Queue stats ──
    try:
        from app.services.job_service import get_queue_stats
        queue_stats = await get_queue_stats(settings.DB_PATH)
        components["queue"] = {"healthy": True, **queue_stats}
    except Exception as exc:
        components["queue"] = {"healthy": False, "error": str(exc)}

    # ── Temp storage ──
    try:
        temp_path = Path(settings.TEMP_DIR)
        temp_path.mkdir(parents=True, exist_ok=True)
        # Check write access
        test_file = temp_path / ".health_check_test"
        test_file.write_text("ok")
        test_file.unlink()
        # Count temp dirs (potential leaked jobs)
        temp_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
        components["temp_storage"] = {
            "healthy": True,
            "writable": True,
            "orphaned_dirs": len(temp_dirs),
        }
    except Exception as exc:
        components["temp_storage"] = {"healthy": False, "error": str(exc)}

    all_healthy = all(c.get("healthy", False) for c in components.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "components": components,
            "timestamp": time.time(),
        },
    )
