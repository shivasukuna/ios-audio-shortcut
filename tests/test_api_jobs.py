"""Tests for job API endpoints.

Covers: job creation, status polling, file download, deletion,
authentication, validation, and edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestJobCreation:
    """Tests for POST /api/v1/jobs."""

    async def test_create_job_success(self, async_client: AsyncClient, auth_headers: dict, sample_job_request: dict):
        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.api.jobs.worker_manager") as mock_wm:
            mock_wm.submit_job.return_value = True
            response = await async_client.post("/api/v1/jobs", json=sample_job_request, headers=auth_headers)
            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "queued"
            assert "status_url" in data
            assert data["status_url"].startswith("/api/v1/jobs/")

    async def test_create_job_no_auth(self, async_client: AsyncClient, sample_job_request: dict):
        response = await async_client.post("/api/v1/jobs", json=sample_job_request)
        assert response.status_code == 401

    async def test_create_job_invalid_auth(self, async_client: AsyncClient, invalid_auth_headers: dict, sample_job_request: dict):
        response = await async_client.post("/api/v1/jobs", json=sample_job_request, headers=invalid_auth_headers)
        assert response.status_code == 401

    async def test_create_job_invalid_url(self, async_client: AsyncClient, auth_headers: dict):
        with patch("app.api.jobs.validate_url", return_value=(False, "Host not in allowed list")):
            response = await async_client.post(
                "/api/v1/jobs",
                json={"url": "https://evil.com/video", "format": "mp3", "quality": "192k"},
                headers=auth_headers,
            )
            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "invalid_url"

    async def test_create_job_missing_url(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.post(
            "/api/v1/jobs",
            json={"format": "mp3", "quality": "192k"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_job_invalid_format(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.post(
            "/api/v1/jobs",
            json={"url": "https://www.instagram.com/reel/test", "format": "wav", "quality": "192k"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_job_invalid_quality(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.post(
            "/api/v1/jobs",
            json={"url": "https://www.instagram.com/reel/test", "format": "mp3", "quality": "999k"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_job_rejects_youtube(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.post(
            "/api/v1/jobs",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "format": "mp3", "quality": "192k"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_url"
        assert "YouTube downloads are not supported" in data["detail"]

    async def test_create_job_ssrf_localhost(self, async_client: AsyncClient, auth_headers: dict):
        with patch("app.api.jobs.validate_url", return_value=(False, "Host resolves to private IP")):
            response = await async_client.post(
                "/api/v1/jobs",
                json={"url": "https://localhost/admin", "format": "mp3", "quality": "192k"},
                headers=auth_headers,
            )
            assert response.status_code == 400

    async def test_create_job_default_format_and_quality(self, async_client: AsyncClient, auth_headers: dict):
        """Test that format and quality default to mp3/192k."""
        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.api.jobs.worker_manager") as mock_wm:
            mock_wm.submit_job.return_value = True
            response = await async_client.post(
                "/api/v1/jobs",
                json={"url": "https://www.instagram.com/reel/test"},
                headers=auth_headers,
            )
            assert response.status_code == 202


@pytest.mark.asyncio
class TestJobStatus:
    """Tests for GET /api/v1/jobs/{job_id}."""

    async def test_get_job_not_found(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get("/api/v1/jobs/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    async def test_get_job_no_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/jobs/some-id")
        assert response.status_code == 401

    async def test_get_existing_job(self, async_client: AsyncClient, auth_headers: dict, sample_job_request: dict):
        """Create a job and then retrieve its status."""
        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.api.jobs.worker_manager") as mock_wm:
            mock_wm.submit_job.return_value = True
            create_resp = await async_client.post("/api/v1/jobs", json=sample_job_request, headers=auth_headers)
            assert create_resp.status_code == 202
            job_id = create_resp.json()["job_id"]

        status_resp = await async_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("queued", "processing", "completed", "failed")


@pytest.mark.asyncio
class TestJobFile:
    """Tests for GET /api/v1/jobs/{job_id}/file."""

    async def test_get_file_not_found(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get("/api/v1/jobs/nonexistent/file", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_file_no_auth_no_token(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/jobs/some-id/file")
        assert response.status_code == 401

    async def test_get_file_invalid_download_token(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/jobs/some-id/file?token=invalid-token")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestJobDeletion:
    """Tests for DELETE /api/v1/jobs/{job_id}."""

    async def test_delete_nonexistent_job(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.delete("/api/v1/jobs/nonexistent", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_no_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/v1/jobs/some-id")
        assert response.status_code == 401

    async def test_delete_existing_job(self, async_client: AsyncClient, auth_headers: dict, sample_job_request: dict):
        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.api.jobs.worker_manager") as mock_wm:
            mock_wm.submit_job.return_value = True
            create_resp = await async_client.post("/api/v1/jobs", json=sample_job_request, headers=auth_headers)
            job_id = create_resp.json()["job_id"]

        delete_resp = await async_client.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
class TestLimitsEndpoint:
    """Tests for GET /api/v1/limits."""

    async def test_get_limits_with_auth(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get("/api/v1/limits", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "max_file_size_mb" in data
        assert "supported_formats" in data
        assert "supported_qualities" in data

    async def test_get_limits_no_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/limits")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestDirectDownload:
    """Tests for GET /api/v1/download and GET /api/v1/jobs/download."""

    async def test_direct_download_success(self, async_client: AsyncClient, auth_headers: dict, temp_dir: Path):
        fake_audio = temp_dir / "direct_song.mp3"
        fake_audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 500)

        mock_result = {
            "filename": "direct_song.mp3",
            "filepath": str(fake_audio),
            "size": len(fake_audio.read_bytes()),
            "duration": 45.0,
        }

        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.services.downloader.download_audio", return_value=mock_result):
            resp = await async_client.get(
                "/api/v1/download",
                params={"url": "https://www.instagram.com/reel/ABC123/"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.headers.get("content-type") == "audio/mpeg"
            assert "direct_song.mp3" in resp.headers.get("content-disposition", "")

    async def test_direct_download_query_token(self, async_client: AsyncClient, temp_dir: Path):
        fake_audio = temp_dir / "direct_song2.mp3"
        fake_audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 500)

        mock_result = {
            "filename": "direct_song2.mp3",
            "filepath": str(fake_audio),
            "size": len(fake_audio.read_bytes()),
            "duration": 45.0,
        }

        with patch("app.api.jobs.validate_url", return_value=(True, "")), \
             patch("app.services.downloader.download_audio", return_value=mock_result):
            resp = await async_client.get(
                "/api/v1/download",
                params={
                    "url": "https://www.instagram.com/reel/ABC123/",
                    "token": "test-token-for-testing-only",
                },
            )
            assert resp.status_code == 200

    async def test_direct_download_unauthorized(self, async_client: AsyncClient):
        resp = await async_client.get(
            "/api/v1/download",
            params={"url": "https://www.instagram.com/reel/ABC123/", "token": "wrong-token"},
        )
        assert resp.status_code == 401

    async def test_direct_download_rejects_youtube(self, async_client: AsyncClient, auth_headers: dict):
        resp = await async_client.get(
            "/api/v1/download",
            params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "YouTube downloads are not supported" in resp.json()["detail"]
