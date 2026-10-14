"""Background media processing worker manager using bounded ThreadPoolExecutor."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import threading
import time
from typing import Any

from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.models.job import JobStatus
from app.services.audio_processor import DownloadException
from app.services.downloader import download_audio
from app.services.job_service import cleanup_expired_jobs, get_job, update_job

logger = get_logger(__name__)


class WorkerManager:
    """Manages worker thread pool, task execution, heartbeat, and cleanup."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._futures: dict[str, Future] = {}
        self._futures_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._heartbeat: float = time.time()
        self._settings: Settings | None = None
        self._cleanup_thread: threading.Thread | None = None

    def start(self, settings: Settings | None = None) -> None:
        """Start the thread pool and background cleanup loop."""
        if settings is None:
            settings = get_settings()
        self._settings = settings

        max_workers = max(1, settings.MAX_CONCURRENT_JOBS)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="media-worker")
        self._shutdown_event.clear()
        self._heartbeat = time.time()

        # Start cleanup daemon thread
        self._cleanup_thread = threading.Thread(
            target=self._run_cleanup_loop,
            daemon=True,
            name="worker-cleanup-thread",
        )
        self._cleanup_thread.start()
        logger.info("WorkerManager started", extra={"max_workers": max_workers})

    def shutdown(self) -> None:
        """Gracefully terminate background workers and cancel pending jobs."""
        logger.info("Shutting down WorkerManager...")
        self._shutdown_event.set()

        with self._futures_lock:
            for job_id, future in self._futures.items():
                if not future.done():
                    future.cancel()
            self._futures.clear()

        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

        logger.info("WorkerManager shutdown completed")

    def is_alive(self) -> bool:
        """Check if worker pool is running and ready."""
        return self._executor is not None and not self._shutdown_event.is_set()

    def get_heartbeat(self) -> float:
        """Get the most recent worker heartbeat timestamp."""
        return self._heartbeat

    def active_job_count(self) -> int:
        """Return the number of jobs currently processing in threads."""
        with self._futures_lock:
            return sum(1 for f in self._futures.values() if not f.done())

    def submit_job(self, job_id: str, url: str) -> bool:
        """Submit a job to be processed by a worker thread."""
        if not self.is_alive() or self._executor is None:
            logger.error("Cannot submit job: worker pool is not active")
            return False

        settings = self._settings or get_settings()

        with self._futures_lock:
            # Check bounded active job capacity
            active = sum(1 for f in self._futures.values() if not f.done())
            if active >= settings.MAX_QUEUE_SIZE:
                logger.warning("Active queue limit reached, cannot submit job", extra={"job_id": job_id})
                return False

            future = self._executor.submit(self._process_job, job_id, url)
            self._futures[job_id] = future

            # Register cleanup callback
            def _on_done(f: Future) -> None:
                with self._futures_lock:
                    self._futures.pop(job_id, None)

            future.add_done_callback(_on_done)

        return True

    def _process_job(self, job_id: str, url: str) -> None:
        """Target function executed in worker thread for a download job."""
        settings = self._settings or get_settings()
        self._heartbeat = time.time()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def _run_async(coro):
            return loop.run_until_complete(coro)

        try:
            # 1. Fetch job record
            job = _run_async(get_job(settings.DB_PATH, job_id))
            if not job or job.is_cancelled:
                logger.info("Job cancelled or not found, skipping processing", extra={"job_id": job_id})
                return

            # 2. Update status to processing
            _run_async(update_job(settings.DB_PATH, job_id, status=JobStatus.PROCESSING.value, progress=0.05))
            logger.info("Worker started processing job", extra={"job_id": job_id})

            # 3. Define progress callback
            last_progress_update = 0.0

            def _progress_hook(d: dict[str, Any]) -> None:
                nonlocal last_progress_update
                self._heartbeat = time.time()
                status_str = d.get("status")
                if status_str == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    if total > 0:
                        pct = round(downloaded / total, 2)
                        now = time.time()
                        if now - last_progress_update >= 1.0:
                            last_progress_update = now
                            _run_async(update_job(settings.DB_PATH, job_id, progress=min(0.9, pct)))

            # 4. Perform media download and extraction
            try:
                result = download_audio(
                    job_id=job_id,
                    url=url,
                    output_format=job.output_format,
                    output_quality=job.output_quality,
                    output_dir=settings.OUTPUT_DIR,
                    temp_dir=settings.TEMP_DIR,
                    progress_callback=_progress_hook,
                    max_filesize_mb=settings.MAX_FILE_SIZE_MB,
                    max_duration_seconds=settings.MAX_DURATION_SECONDS,
                )

                # Mark completed
                _run_async(
                    update_job(
                        settings.DB_PATH,
                        job_id,
                        status=JobStatus.COMPLETED.value,
                        progress=1.0,
                        output_filename=result["filename"],
                        output_size=result["size"],
                        error_code=None,
                        error_message=None,
                    )
                )
                self._heartbeat = time.time()
                logger.info("Job marked completed", extra={"job_id": job_id, "file": result["filename"]})

            except DownloadException as exc:
                logger.warning("Job failed with DownloadException", extra={"job_id": job_id, "error": exc.message})
                _run_async(
                    update_job(
                        settings.DB_PATH,
                        job_id,
                        status=JobStatus.FAILED.value,
                        error_code=exc.error_code,
                        error_message=exc.message[:500],
                    )
                )
            except Exception as exc:
                logger.exception("Job failed with unhandled exception", extra={"job_id": job_id})
                _run_async(
                    update_job(
                        settings.DB_PATH,
                        job_id,
                        status=JobStatus.FAILED.value,
                        error_code="internal_error",
                        error_message=str(exc)[:500],
                    )
                )
            finally:
                self._heartbeat = time.time()
        finally:
            try:
                # Cancel any pending tasks in the loop
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                loop.close()

    def _run_cleanup_loop(self) -> None:
        """Periodic background maintenance loop for removing expired files."""
        settings = self._settings or get_settings()
        while not self._shutdown_event.is_set():
            try:
                self._heartbeat = time.time()
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(cleanup_expired_jobs(settings.DB_PATH, settings.OUTPUT_DIR))
                finally:
                    loop.close()
            except Exception as exc:
                logger.error("Error in background cleanup loop", extra={"error": str(exc)})

            # Sleep 60 seconds with responsive shutdown checking
            self._shutdown_event.wait(timeout=60)


# Module-level singleton
worker_manager = WorkerManager()
