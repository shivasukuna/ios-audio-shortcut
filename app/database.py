"""Asynchronous SQLite database management using aiosqlite.

Manages SQLite connection lifecycle, schema initialization with WAL mode,
indices for high-frequency queries, and automatic recovery of interrupted jobs.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# SQL DDL for jobs table and indexes
CREATE_JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL,
    source_url_hash TEXT NOT NULL,
    source_host TEXT NOT NULL,
    output_format TEXT NOT NULL,
    output_quality TEXT NOT NULL,
    output_filename TEXT,
    output_size INTEGER,
    error_code TEXT,
    error_message TEXT,
    expires_at TEXT NOT NULL,
    cancelled INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_INDEX_STATUS_SQL = """
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

CREATE_INDEX_SOURCE_URL_HASH_SQL = """
CREATE INDEX IF NOT EXISTS idx_jobs_source_url_hash ON jobs(source_url_hash);
"""


def _ensure_db_dir(path: Path) -> None:
    """Ensure parent directory for SQLite database file exists.

    Args:
        path: Path to the database file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


async def init_db(db_path: str | Path | None = None) -> None:
    """Initialize the SQLite database schema and enable write-ahead logging (WAL).

    Args:
        db_path: Optional explicit path to the database file. If omitted,
                 the path is retrieved from application settings.
    """
    settings = get_settings()
    target_path = Path(db_path) if db_path is not None else Path(settings.DB_PATH)
    _ensure_db_dir(target_path)

    logger.info("Initializing database schema", extra={"db_path": str(target_path)})
    async with aiosqlite.connect(target_path) as conn:
        # Enable WAL mode for high concurrency between readers and writers
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        await conn.execute("PRAGMA foreign_keys = ON;")

        # Create schema and indices
        await conn.execute(CREATE_JOBS_TABLE_SQL)
        await conn.execute(CREATE_INDEX_STATUS_SQL)
        await conn.execute(CREATE_INDEX_SOURCE_URL_HASH_SQL)
        await conn.commit()

    logger.info("Database schema initialized successfully")


@asynccontextmanager
async def get_db(
    db_path: str | Path | None = None,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields an active aiosqlite connection.

    Row factory is automatically configured to aiosqlite.Row for dict-like
    column access. Transactions are committed on normal exit or rolled back
    if an unhandled exception occurs.

    Args:
        db_path: Optional explicit database path override.

    Yields:
        aiosqlite.Connection: Configured database connection.
    """
    settings = get_settings()
    target_path = Path(db_path) if db_path is not None else Path(settings.DB_PATH)
    _ensure_db_dir(target_path)

    async with aiosqlite.connect(target_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


async def recover_stale_jobs(db_path: str | Path | None = None) -> int:
    """Recover jobs left in 'processing' status due to an ungraceful server termination.

    Marks all 'processing' records as 'failed' with error code 'server_restart'.

    Args:
        db_path: Optional explicit database path override.

    Returns:
        int: Number of stale jobs recovered.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    recovery_sql = """
    UPDATE jobs
    SET status = 'failed',
        error_code = 'server_restart',
        error_message = 'Job was interrupted by a server restart',
        updated_at = ?
    WHERE status = 'processing';
    """
    async with get_db(db_path) as conn:
        cursor = await conn.execute(recovery_sql, (now_iso,))
        recovered_count = cursor.rowcount

    if recovered_count > 0:
        logger.warning(
            "Recovered stale in-progress jobs on startup",
            extra={"recovered_count": recovered_count},
        )
    else:
        logger.info("No stale in-progress jobs detected during startup recovery")

    return recovered_count
