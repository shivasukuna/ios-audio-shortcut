"""FastAPI application entrypoint.

Sets up the application lifespan, routers, and middleware.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import init_db, recover_stale_jobs
from app.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize on startup, cleanup on shutdown."""
    settings = get_settings()

    # ── Startup ──
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Audio Downloader API", extra={"version": "0.1.0"})

    # Initialize database
    await init_db(settings.DB_PATH)
    logger.info("Database initialized")

    # Recover stale jobs from previous crash
    recovered = await recover_stale_jobs(settings.DB_PATH)
    if recovered > 0:
        logger.warning("Recovered stale jobs", extra={"count": recovered})

    # Start worker pool
    from app.workers.worker import worker_manager

    worker_manager.start(settings)
    logger.info("Worker pool started", extra={"max_workers": settings.MAX_CONCURRENT_JOBS})

    yield

    # ── Shutdown ──
    logger.info("Shutting down...")
    worker_manager.shutdown()
    logger.info("Worker pool stopped")
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="Audio Downloader API",
        description="Self-hosted audio downloader backend for iOS Shortcuts",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.LOG_LEVEL == "DEBUG" else None,
        redoc_url=None,
    )

    # ── Include routers ──
    from app.api.health import router as health_router
    from app.api.jobs import download_direct, router as jobs_router
    from app.api.limits import router as limits_router

    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(limits_router)
    app.add_api_route("/api/v1/download", download_direct, methods=["GET"], summary="Direct audio download alias")

    # ── Exception handlers ──

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return consistent JSON error for validation failures."""
        errors = exc.errors()
        first_error = errors[0] if errors else {"msg": "Validation error"}
        field = ".".join(str(loc) for loc in first_error.get("loc", []))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "detail": f"{field}: {first_error.get('msg', 'Invalid value')}",
                "code": "VALIDATION_ERROR",
            },
        )

    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException | StarletteHTTPException
    ) -> JSONResponse:
        """Un-nest dict details to guarantee consistent top-level JSON error contract."""
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "error",
                "detail": str(exc.detail),
                "code": f"HTTP_{exc.status_code}",
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all handler to prevent stack traces leaking to clients."""
        logger.exception("Unhandled exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred",
                "code": "INTERNAL_ERROR",
            },
        )

    # ── Request logging middleware ──

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        """Log every request with timing information."""
        start_time = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)

        # Don't log health check spam at INFO level
        path = request.url.path
        log_level = "DEBUG" if path.startswith("/health/live") else "INFO"

        log_method = logger.debug if log_level == "DEBUG" else logger.info
        log_method(
            "Request completed",
            extra={
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else "unknown",
            },
        )

        return response

    return app


# Create the application instance
app = create_app()
