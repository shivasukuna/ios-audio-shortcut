"""Media downloader wrapper for yt-dlp with audio post-processing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse

import yt_dlp
import yt_dlp.utils

from app.logging_config import get_logger
from app.services.audio_processor import DownloadException, validate_audio_file
from app.services.security import sanitize_filename

logger = get_logger(__name__)


def download_audio(
    job_id: str,
    url: str,
    output_format: str,
    output_quality: str,
    output_dir: str,
    temp_dir: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    max_filesize_mb: int = 100,
    max_duration_seconds: int = 1800,
) -> dict[str, Any]:
    """Download media using yt-dlp, extract/convert audio, and move to final output directory.

    Args:
        job_id: Unique job identifier.
        url: Validated media URL.
        output_format: Audio format (mp3, aac, opus, m4a).
        output_quality: Audio quality/bitrate (128k, 192k, 320k, best).
        output_dir: Destination base directory for finished audio.
        temp_dir: Scratch workspace base directory.
        progress_callback: Optional callable receiving yt-dlp progress dicts.
        max_filesize_mb: Max allowed file size in MB.
        max_duration_seconds: Max allowed media duration in seconds.

    Returns:
        dict with filename, filepath, size, and duration.

    Raises:
        DownloadException: Upon extraction, conversion, or validation errors.
    """
    job_temp = Path(temp_dir) / job_id
    job_temp.mkdir(parents=True, exist_ok=True)

    job_output = Path(output_dir) / job_id
    job_output.mkdir(parents=True, exist_ok=True)

    # Redact URL in logging, logging only host
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
    except Exception:
        host = "unknown"
    logger.info("Initiating audio download", extra={"job_id": job_id, "host": host, "format": output_format})

    # Prepare quality string for FFmpegExtractAudio
    quality_arg = output_quality.rstrip("kK") if output_quality != "best" else "0"

    ydl_opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(job_temp / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "max_filesize": max_filesize_mb * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 3,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }

    # Duration filtering
    if max_duration_seconds > 0:
        ydl_opts["match_filter"] = yt_dlp.utils.match_filter_func(f"duration <= {max_duration_seconds}")

    # Audio extraction postprocessor
    if output_format in {"mp3", "aac", "opus", "m4a"}:
        postprocessor: dict[str, Any] = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": output_format,
        }
        if output_quality != "best":
            postprocessor["preferredquality"] = quality_arg
        ydl_opts["postprocessors"] = [postprocessor]

    # Progress hook
    if progress_callback is not None:
        def _hook(d: dict[str, Any]) -> None:
            try:
                progress_callback(d)
            except Exception as exc:
                logger.debug("Progress callback error", extra={"error": str(exc)})

        ydl_opts["progress_hooks"] = [_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        logger.warning("yt-dlp download failed", extra={"job_id": job_id, "error": str(exc)})
        raise DownloadException("download_failed", str(exc)) from exc
    except yt_dlp.utils.ExtractorError as exc:
        logger.warning("yt-dlp extraction failed", extra={"job_id": job_id, "error": str(exc)})
        raise DownloadException("extraction_failed", str(exc)) from exc
    except yt_dlp.utils.PostProcessingError as exc:
        logger.warning("yt-dlp post-processing failed", extra={"job_id": job_id, "error": str(exc)})
        raise DownloadException("conversion_failed", str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error during media processing", extra={"job_id": job_id, "error": str(exc)})
        raise DownloadException("unknown_error", str(exc)) from exc

    # Find the resulting audio file in job_temp
    audio_files = [
        f
        for f in job_temp.iterdir()
        if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
    ]

    if not audio_files:
        # Clean up empty temp
        shutil.rmtree(job_temp, ignore_errors=True)
        raise DownloadException("no_output", "No audio file produced")

    # Pick the largest or newest audio file
    source_file = sorted(audio_files, key=lambda f: f.stat().st_size, reverse=True)[0]

    # Validate audio file
    validation = validate_audio_file(source_file)
    if not validation.get("valid", False):
        shutil.rmtree(job_temp, ignore_errors=True)
        err = validation.get("error") or "Generated audio file failed validation"
        raise DownloadException("invalid_audio", err)

    # Sanitize and move to final output directory
    safe_name = sanitize_filename(source_file.name)
    target_path = job_output / safe_name

    # If already exists, overwrite
    if target_path.exists():
        target_path.unlink()

    shutil.move(str(source_file), str(target_path))

    # Clean up temp folder
    shutil.rmtree(job_temp, ignore_errors=True)

    file_size = target_path.stat().st_size
    duration = float(validation.get("duration", 0.0))

    logger.info("Audio processed successfully", extra={"job_id": job_id, "output_file": safe_name, "size": file_size})

    return {
        "filename": safe_name,
        "filepath": str(target_path),
        "size": file_size,
        "duration": duration,
    }
