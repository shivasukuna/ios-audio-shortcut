"""Tests for the WorkerManager and background task execution."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import pytest

from app.models.job import JobStatus
from app.services.audio_processor import DownloadException
from app.services.job_service import create_job, get_job
from app.workers.worker import WorkerManager


@pytest.mark.asyncio
class TestWorkerManager:
    """Tests for WorkerManager lifecycle, queue management, and job execution."""

    async def test_worker_lifecycle(self, test_settings):
        wm = WorkerManager()
        assert not wm.is_alive()

        wm.start(test_settings)
        assert wm.is_alive()
        assert wm.get_heartbeat() > 0

        wm.shutdown()
        assert not wm.is_alive()

    async def test_process_job_success(self, test_settings, initialized_db):
        """Test processing a job to completion."""
        wm = WorkerManager()
        wm.start(test_settings)

        job = await create_job(
            db_path=test_settings.DB_PATH,
            url_hash="mock-hash-1",
            source_host="www.instagram.com",
            output_format="mp3",
            output_quality="192k",
        )

        mock_result = {
            "filename": "test_song.mp3",
            "filepath": str(Path(test_settings.OUTPUT_DIR) / job.id / "test_song.mp3"),
            "size": 123456,
            "duration": 180.0,
        }

        with patch("app.workers.worker.download_audio", return_value=mock_result):
            wm.submit_job(job.id, "https://www.instagram.com/reel/mock1")

            # Wait for thread to finish
            for _ in range(50):
                await asyncio.sleep(0.1)
                updated = await get_job(test_settings.DB_PATH, job.id)
                if updated and updated.status == JobStatus.COMPLETED.value:
                    break

            updated = await get_job(test_settings.DB_PATH, job.id)
            assert updated is not None
            assert updated.status == JobStatus.COMPLETED.value
            assert updated.output_filename == "test_song.mp3"
            assert updated.output_size == 123456

        wm.shutdown()

    async def test_process_job_failure(self, test_settings, initialized_db):
        """Test handling of DownloadException in worker."""
        wm = WorkerManager()
        wm.start(test_settings)

        job = await create_job(
            db_path=test_settings.DB_PATH,
            url_hash="mock-hash-fail",
            source_host="www.instagram.com",
            output_format="mp3",
            output_quality="192k",
        )

        with patch("app.workers.worker.download_audio", side_effect=DownloadException("extraction_failed", "Video unavailable")):
            wm.submit_job(job.id, "https://www.instagram.com/reel/fail")

            for _ in range(50):
                await asyncio.sleep(0.1)
                updated = await get_job(test_settings.DB_PATH, job.id)
                if updated and updated.status == JobStatus.FAILED.value:
                    break

            updated = await get_job(test_settings.DB_PATH, job.id)
            assert updated is not None
            assert updated.status == JobStatus.FAILED.value
            assert updated.error_code == "extraction_failed"

        wm.shutdown()
