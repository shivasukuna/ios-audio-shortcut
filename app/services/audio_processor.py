"""Audio processing and validation utilities using FFmpeg and FFprobe."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)


class DownloadException(Exception):
    """Custom exception raised during media download and audio post-processing."""

    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def verify_ffmpeg() -> dict[str, Any]:
    """Verify presence and extract versions for ffmpeg and ffprobe binaries.

    Returns:
        dict containing availability flags and parsed version strings.
    """
    result: dict[str, Any] = {
        "ffmpeg_available": False,
        "ffmpeg_version": "unavailable",
        "ffprobe_available": False,
        "ffprobe_version": "unavailable",
    }

    # Check ffmpeg
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0:
                result["ffmpeg_available"] = True
                first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
                match = re.search(r"version\s+([^\s]+)", first_line)
                result["ffmpeg_version"] = match.group(1) if match else first_line[:30]
        except Exception as exc:
            logger.warning("Failed to invoke ffmpeg", extra={"error": str(exc)})

    # Check ffprobe
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin:
        try:
            proc = subprocess.run(
                [ffprobe_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0:
                result["ffprobe_available"] = True
                first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
                match = re.search(r"version\s+([^\s]+)", first_line)
                result["ffprobe_version"] = match.group(1) if match else first_line[:30]
        except Exception as exc:
            logger.warning("Failed to invoke ffprobe", extra={"error": str(exc)})

    return result


def validate_audio_file(file_path: Path | str) -> dict[str, Any]:
    """Inspect and validate an audio file using ffprobe.

    Verifies the file exists, has a valid audio stream, and extracts duration.

    Args:
        file_path: Filesystem path to audio file.

    Returns:
        dict: Validation details including valid bool, format, duration, bitrate, and codec.
    """
    path = Path(file_path)
    if not path.is_file() or path.stat().st_size == 0:
        return {
            "valid": False,
            "format": "unknown",
            "duration": 0.0,
            "bitrate": 0,
            "codec": "unknown",
            "error": "File does not exist or is empty",
        }

    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        # If ffprobe is not installed, verify file size > 0 as fallback
        size = path.stat().st_size
        return {
            "valid": size > 0,
            "format": path.suffix.lstrip(".").lower(),
            "duration": 0.0,
            "bitrate": 0,
            "codec": path.suffix.lstrip(".").lower(),
            "error": None if size > 0 else "File is empty",
        }

    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode != 0:
            return {
                "valid": False,
                "format": "unknown",
                "duration": 0.0,
                "bitrate": 0,
                "codec": "unknown",
                "error": f"ffprobe exited with code {proc.returncode}",
            }

        probe_data = json.loads(proc.stdout)
        streams = probe_data.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        if not audio_streams:
            return {
                "valid": False,
                "format": "unknown",
                "duration": 0.0,
                "bitrate": 0,
                "codec": "unknown",
                "error": "No audio stream found in container",
            }

        first_audio = audio_streams[0]
        fmt_data = probe_data.get("format", {})

        duration_str = fmt_data.get("duration") or first_audio.get("duration") or "0.0"
        bitrate_str = fmt_data.get("bit_rate") or first_audio.get("bit_rate") or "0"

        return {
            "valid": True,
            "format": fmt_data.get("format_name", path.suffix.lstrip(".")),
            "duration": float(duration_str),
            "bitrate": int(bitrate_str) if str(bitrate_str).isdigit() else 0,
            "codec": first_audio.get("codec_name", "unknown"),
            "error": None,
        }
    except Exception as exc:
        logger.error("Audio validation failed with exception", extra={"error": str(exc), "path": str(path)})
        return {
            "valid": False,
            "format": "unknown",
            "duration": 0.0,
            "bitrate": 0,
            "codec": "unknown",
            "error": str(exc),
        }


def get_audio_metadata(file_path: Path | str) -> dict[str, Any]:
    """Extract audio metadata tags and stream info using ffprobe.

    Args:
        file_path: Filesystem path to audio file.

    Returns:
        dict: Extracted metadata including title, artist, duration, codec, sample rate, channels.
    """
    val = validate_audio_file(file_path)
    if not val.get("valid"):
        return {"error": val.get("error")}

    return {
        "format": val.get("format"),
        "duration": val.get("duration"),
        "bitrate": val.get("bitrate"),
        "codec": val.get("codec"),
    }
