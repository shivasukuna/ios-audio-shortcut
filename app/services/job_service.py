"""Job service managing asynchronous SQLite operations for job lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
from typing import Any
import uuid

import aiosqlite

from app.database import get_db
from app.logging_config import get_logger
from app.models.job import Job, JobStatus

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


async def create_job(
    db_path: str,
    url_hash: str,
    source_host: str,
    output_format: str,
    output_quality: str,
    original_url: str = "",
    artifact_ttl: int = 3600,
) -> Job:
    """Create a new job record or return existing active job for duplicate URLs.

    Args:
        db_path: Path to the SQLite database.
        url_hash: SHA-256 hash of the source media URL.
        source_host: Domain hostname of the media source.
        output_format: Audio format (mp3, aac, opus, etc.).
        output_quality: Audio quality setting (128k, 192k, etc.).
        original_url: Full URL (not stored in DB for privacy).
        artifact_ttl: Lifetime in seconds before output artifacts expire.

    Returns:
        Job: Newly created or pre-existing active Job model.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_at = datetime.fromtimestamp(now.timestamp() + artifact_ttl, timezone.utc).isoformat()

    async with get_db(db_path) as db:
        # Check for existing active job with same url_hash
        cursor = await db.execute(
            """
            SELECT * FROM jobs
            WHERE source_url_hash = ? AND status IN ('queued', 'processing')
            LIMIT 1
            """,
            (url_hash,),
        )
        row = await cursor.fetchone()
        if row:
            logger.info("Reusing active duplicate job", extra={"job_id": row["id"]})
            return Job.from_row(row)

        job_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO jobs (
                id, created_at, updated_at, status, progress,
                source_url_hash, source_host, output_format, output_quality,
                output_filename, output_size, error_code, error_message,
                expires_at, cancelled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                now_iso,
                now_iso,
                JobStatus.QUEUED.value,
                0.0,
                url_hash,
                source_host,
                output_format,
                output_quality,
                None,
                None,
                None,
                None,
                expires_at,
                0,
            ),
        )
        await db.commit()

        # Retrieve freshly created job
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        new_row = await cursor.fetchone()
        return Job.from_row(new_row)


async def get_job(db_path: str, job_id: str) -> Job | None:
    """Retrieve a job by its ID, checking for expiration.

    Args:
        db_path: Path to the database.
        job_id: Unique job identifier.

    Returns:
        Job or None if not found.
    """
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        job = Job.from_row(row)

        # Check expiration
        try:
            expires_dt = datetime.fromisoformat(job.expires_at)
            if datetime.now(timezone.utc) > expires_dt and job.status not in (JobStatus.EXPIRED.value, JobStatus.PROCESSING.value):
                # Mark as expired
                await db.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                    (JobStatus.EXPIRED.value, _utc_now_iso(), job.id),
                )
                await db.commit()
                job.status = JobStatus.EXPIRED.value
        except Exception:
            pass

        return job


async def update_job(db_path: str, job_id: str, **kwargs: Any) -> Job | None:
    """Update job columns dynamically.

    Args:
        db_path: Path to database.
        job_id: Job ID to update.
        **kwargs: Column names and new values.

    Returns:
        Updated Job or None if not found.
    """
    if not kwargs:
        return await get_job(db_path, job_id)

    kwargs["updated_at"] = _utc_now_iso()

    columns = [f"{k} = ?" for k in kwargs]
    values = list(kwargs.values())
    values.append(job_id)

    query = f"UPDATE jobs SET {', '.join(columns)} WHERE id = ?"

    async with get_db(db_path) as db:
        await db.execute(query, values)
        await db.commit()

        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return Job.from_row(row) if row else None


async def delete_job(db_path: str, job_id: str, output_dir: str) -> bool:
    """Mark job cancelled and remove any generated output files.

    Args:
        db_path: Path to SQLite DB.
        job_id: Job ID to cancel/delete.
        output_dir: Base directory holding audio outputs.

    Returns:
        bool: True if job existed and was updated, False otherwise.
    """
    now_iso = _utc_now_iso()
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return False

        await db.execute(
            """
            UPDATE jobs
            SET status = ?, cancelled = 1, updated_at = ?
            WHERE id = ?
            """,
            (JobStatus.CANCELLED.value, now_iso, job_id),
        )
        await db.commit()

    # Remove disk directory
    job_dir = Path(output_dir) / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

    return True


async def get_queue_depth(db_path: str) -> int:
    """Count number of jobs currently in 'queued' status."""
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'queued'")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def get_active_count(db_path: str) -> int:
    """Count total active jobs (queued + processing)."""
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'processing')")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def get_queue_stats(db_path: str) -> dict[str, Any]:
    """Retrieve queue health statistics including status counts and oldest job age."""
    stats: dict[str, Any] = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "oldest_job_age_seconds": 0.0,
    }

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        rows = await cursor.fetchall()
        for row in rows:
            status_name = str(row[0])
            if status_name in stats:
                stats[status_name] = int(row[1])

        # Find oldest queued job
        cursor = await db.execute(
            "SELECT created_at FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        )
        oldest_row = await cursor.fetchone()
        if oldest_row:
            try:
                created_dt = datetime.fromisoformat(str(oldest_row[0]))
                stats["oldest_job_age_seconds"] = max(
                    0.0, (datetime.now(timezone.utc) - created_dt).total_seconds()
                )
            except Exception:
                pass

    return stats


async def cleanup_expired_jobs(db_path: str, output_dir: str) -> int:
    """Clean up expired output directories and update job records.

    Returns:
        int: Number of jobs marked expired.
    """
    now_iso = _utc_now_iso()
    cleaned_count = 0

    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            SELECT id FROM jobs
            WHERE expires_at < ? AND status IN ('completed', 'failed', 'cancelled')
            """,
            (now_iso,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            job_id = str(row[0])
            job_dir = Path(output_dir) / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)

            await db.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (JobStatus.EXPIRED.value, now_iso, job_id),
            )
            cleaned_count += 1

        if cleaned_count > 0:
            await db.commit()
            logger.info("Cleaned up expired jobs", extra={"count": cleaned_count})

    return cleaned_count
