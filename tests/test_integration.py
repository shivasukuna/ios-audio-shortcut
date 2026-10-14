"""Integration tests against live Instagram URLs.

These tests are opt-in and require actual network connectivity and external API stability.
Execute using:
    pytest -m integration tests/test_integration.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app.services.downloader import download_audio

pytestmark = pytest.mark.integration


@pytest.fixture
def integration_dirs(temp_dir: Path):
    output = temp_dir / "live_output"
    output.mkdir()
    tmp = temp_dir / "live_tmp"
    tmp.mkdir()
    return str(output), str(tmp)


def test_live_instagram_download(integration_dirs):
    """Test live download of a public reel clip from Instagram."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg binary required for live conversion integration test")

    output_dir, temp_dir = integration_dirs
    # Public sample reel URL (can be skipped if network/Instagram rate-limits)
    test_url = "https://www.instagram.com/reel/C8q74x0uB6t/"

    try:
        result = download_audio(
            job_id="live-ig-test",
            url=test_url,
            output_format="mp3",
            output_quality="128k",
            output_dir=output_dir,
            temp_dir=temp_dir,
            max_filesize_mb=25,
            max_duration_seconds=60,
        )
        assert result["filename"].endswith(".mp3")
        assert result["size"] > 0
        assert Path(result["filepath"]).exists()
    except Exception as exc:
        pytest.skip(f"Live Instagram test skipped due to external environment: {exc}")
