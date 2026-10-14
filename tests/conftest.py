"""Pytest fixtures for the Audio Downloader test suite."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment variables BEFORE importing app modules
os.environ["API_TOKEN"] = "test-token-for-testing-only"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="audio_test_", ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_dir: Path):
    """Create test settings with temporary directories."""
    from app.config import Settings

    db_dir = temp_dir / "db"
    db_dir.mkdir()
    output_dir = temp_dir / "output"
    output_dir.mkdir()
    tmp_dir = temp_dir / "tmp"
    tmp_dir.mkdir()

    return Settings(
        API_TOKEN="test-token-for-testing-only",
        MAX_CONCURRENT_JOBS=2,
        MAX_QUEUE_SIZE=5,
        MAX_FILE_SIZE_MB=10,
        MAX_DURATION_SECONDS=300,
        JOB_TIMEOUT_SECONDS=30,
        ARTIFACT_TTL_SECONDS=600,
        DOWNLOAD_TOKEN_TTL_SECONDS=60,
        OUTPUT_DIR=str(output_dir),
        TEMP_DIR=str(tmp_dir),
        DB_PATH=str(db_dir / "test.db"),
        LOG_LEVEL="DEBUG",
        RATE_LIMIT_REQUESTS=100,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return valid authentication headers."""
    return {"Authorization": "Bearer test-token-for-testing-only"}


@pytest.fixture
def invalid_auth_headers() -> dict[str, str]:
    """Return invalid authentication headers."""
    return {"Authorization": "Bearer wrong-token"}


@pytest_asyncio.fixture
async def initialized_db(test_settings) -> AsyncGenerator[str, None]:
    """Initialize a test database and return the DB path."""
    from app.database import init_db

    await init_db(test_settings.DB_PATH)
    yield test_settings.DB_PATH


@pytest_asyncio.fixture
async def async_client(test_settings, temp_dir) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with the app configured for testing."""
    from app.config import get_settings
    from app.database import init_db

    # Override settings
    get_settings.cache_clear()
    os.environ["DB_PATH"] = test_settings.DB_PATH
    os.environ["OUTPUT_DIR"] = test_settings.OUTPUT_DIR
    os.environ["TEMP_DIR"] = test_settings.TEMP_DIR

    # Initialize database
    await init_db(test_settings.DB_PATH)

    # Import app after setting env vars
    from app.main import create_app

    app = create_app()

    # Reset rate limiter for each test
    from app.api.dependencies import reset_rate_limiter
    reset_rate_limiter()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    get_settings.cache_clear()


@pytest.fixture
def mock_worker_manager():
    """Create a mock worker manager that doesn't actually process jobs."""
    manager = MagicMock()
    manager.is_alive.return_value = True
    manager.get_heartbeat.return_value = 0.0
    manager.active_job_count.return_value = 0
    manager.submit_job.return_value = True
    return manager


@pytest.fixture
def sample_instagram_url() -> str:
    """Return a sample Instagram URL for testing."""
    return "https://www.instagram.com/reel/ABC123/"


@pytest.fixture
def sample_job_request() -> dict:
    """Return a sample job creation request body."""
    return {
        "url": "https://www.instagram.com/reel/ABC123/",
        "format": "mp3",
        "quality": "192k",
    }
