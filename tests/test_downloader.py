"""Tests for the downloader service.

Uses mocked yt-dlp to test download logic without network access.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.downloader import DownloadException, download_audio


class TestDownloadAudio:
    """Tests for the download_audio function with mocked yt-dlp."""

    def _create_fake_audio(self, directory: Path, filename: str = "test_song.mp3") -> Path:
        """Create a fake audio file for testing."""
        filepath = directory / filename
        # Write minimal valid-looking content
        filepath.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1000)
        return filepath

    @patch("app.services.downloader.yt_dlp.YoutubeDL")
    @patch("app.services.downloader.validate_audio_file")
    def test_successful_download(self, mock_validate, mock_ytdl_class, temp_dir: Path):
        """Test a successful audio download and conversion."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        dl_temp_dir = temp_dir / "tmp"
        dl_temp_dir.mkdir()

        # Setup mock
        mock_ytdl = MagicMock()
        mock_ytdl_class.return_value.__enter__ = MagicMock(return_value=mock_ytdl)
        mock_ytdl_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ytdl.download.return_value = 0

        # Create a fake output file that yt-dlp would produce
        job_temp = dl_temp_dir / "test-job-id"
        job_temp.mkdir()
        fake_file = self._create_fake_audio(job_temp, "Test Song.mp3")

        mock_validate.return_value = {"valid": True, "duration": 180.0, "format": "mp3"}

        result = download_audio(
            job_id="test-job-id",
            url="https://www.youtube.com/watch?v=test",
            output_format="mp3",
            output_quality="192k",
            output_dir=str(output_dir),
            temp_dir=str(dl_temp_dir),
            progress_callback=None,
            max_filesize_mb=100,
            max_duration_seconds=1800,
        )

        assert result["filename"] is not None
        assert result["size"] > 0

    @patch("app.services.downloader.yt_dlp.YoutubeDL")
    def test_download_error_raises_exception(self, mock_ytdl_class, temp_dir: Path):
        """Test that yt-dlp download errors are properly wrapped."""
        import yt_dlp.utils

        output_dir = temp_dir / "output"
        output_dir.mkdir()
        dl_temp_dir = temp_dir / "tmp"
        dl_temp_dir.mkdir()

        mock_ytdl = MagicMock()
        mock_ytdl_class.return_value.__enter__ = MagicMock(return_value=mock_ytdl)
        mock_ytdl_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ytdl.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

        with pytest.raises(DownloadException) as exc_info:
            download_audio(
                job_id="test-job-fail",
                url="https://www.youtube.com/watch?v=invalid",
                output_format="mp3",
                output_quality="192k",
                output_dir=str(output_dir),
                temp_dir=str(dl_temp_dir),
                progress_callback=None,
                max_filesize_mb=100,
                max_duration_seconds=1800,
            )

        assert exc_info.value.error_code == "download_failed"

    @patch("app.services.downloader.yt_dlp.YoutubeDL")
    def test_no_output_file_raises_exception(self, mock_ytdl_class, temp_dir: Path):
        """Test that missing output file after download raises error."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        dl_temp_dir = temp_dir / "tmp"
        dl_temp_dir.mkdir()

        mock_ytdl = MagicMock()
        mock_ytdl_class.return_value.__enter__ = MagicMock(return_value=mock_ytdl)
        mock_ytdl_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ytdl.download.return_value = 0
        # Don't create any output file — simulates yt-dlp failing silently

        with pytest.raises(DownloadException) as exc_info:
            download_audio(
                job_id="test-job-nofile",
                url="https://www.youtube.com/watch?v=test",
                output_format="mp3",
                output_quality="192k",
                output_dir=str(output_dir),
                temp_dir=str(dl_temp_dir),
                progress_callback=None,
                max_filesize_mb=100,
                max_duration_seconds=1800,
            )

        assert exc_info.value.error_code == "no_output"

    def test_download_exception_has_correct_fields(self):
        """Test DownloadException carries error_code and message."""
        exc = DownloadException("test_code", "Test error message")
        assert exc.error_code == "test_code"
        assert exc.message == "Test error message"
        assert str(exc) == "Test error message"


class TestDownloadExceptionTypes:
    """Test that various failure modes produce correct error codes."""

    @patch("app.services.downloader.yt_dlp.YoutubeDL")
    def test_extractor_error(self, mock_ytdl_class, temp_dir: Path):
        import yt_dlp.utils

        output_dir = temp_dir / "output"
        output_dir.mkdir()
        dl_temp_dir = temp_dir / "tmp"
        dl_temp_dir.mkdir()

        mock_ytdl = MagicMock()
        mock_ytdl_class.return_value.__enter__ = MagicMock(return_value=mock_ytdl)
        mock_ytdl_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ytdl.download.side_effect = yt_dlp.utils.ExtractorError("Could not extract")

        with pytest.raises(DownloadException) as exc_info:
            download_audio(
                job_id="test-extractor-err",
                url="https://www.youtube.com/watch?v=test",
                output_format="mp3",
                output_quality="192k",
                output_dir=str(output_dir),
                temp_dir=str(dl_temp_dir),
                progress_callback=None,
                max_filesize_mb=100,
                max_duration_seconds=1800,
            )

        assert exc_info.value.error_code == "extraction_failed"
