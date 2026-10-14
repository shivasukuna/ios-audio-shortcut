"""Tests for health check endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestLiveness:
    """Tests for GET /health/live."""

    async def test_liveness_returns_200(self, async_client: AsyncClient):
        response = await async_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    async def test_liveness_no_auth_required(self, async_client: AsyncClient):
        """Liveness should work without authentication."""
        response = await async_client.get("/health/live")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestReadiness:
    """Tests for GET /health/ready."""

    async def test_readiness_returns_checks(self, async_client: AsyncClient):
        response = await async_client.get("/health/ready")
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "worker_pool" in data["checks"]

    async def test_readiness_no_auth_required(self, async_client: AsyncClient):
        response = await async_client.get("/health/ready")
        assert response.status_code in (200, 503)


@pytest.mark.asyncio
class TestDeepHealth:
    """Tests for GET /health/deep."""

    async def test_deep_health_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/health/deep")
        assert response.status_code == 401

    async def test_deep_health_with_auth(self, async_client: AsyncClient, auth_headers: dict):
        response = await async_client.get("/health/deep", headers=auth_headers)
        # May be 200 or 503 depending on worker state, but should not be 401
        assert response.status_code in (200, 503)
        data = response.json()
        assert "components" in data
        assert "database" in data["components"]
        assert "ffmpeg" in data["components"]
        assert "yt_dlp" in data["components"]
        assert "disk" in data["components"]

    async def test_deep_health_rejects_invalid_auth(
        self, async_client: AsyncClient, invalid_auth_headers: dict
    ):
        response = await async_client.get("/health/deep", headers=invalid_auth_headers)
        assert response.status_code == 401
