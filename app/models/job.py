"""Data models and enums representing download jobs."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiosqlite


class JobStatus(str, Enum):
    """Lifecycle status states for an audio extraction job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class Job:
    """Represents an audio download job stored in SQLite.

    Matches the database schema defined in app/database.py.
    """

    id: str
    created_at: str
    updated_at: str
    source_url_hash: str
    source_host: str
    output_format: str
    output_quality: str
    expires_at: str
    status: str = JobStatus.QUEUED.value
    progress: float | None = None
    output_filename: str | None = None
    output_size: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancelled: int = 0

    def __post_init__(self) -> None:
        """Normalize status and types if enums or integers are passed."""
        if isinstance(self.status, JobStatus):
            self.status = self.status.value

    @property
    def is_cancelled(self) -> bool:
        """Return True if job is marked as cancelled or has cancelled flag set."""
        return bool(self.cancelled) or self.status == JobStatus.CANCELLED.value

    @property
    def is_terminal(self) -> bool:
        """Return True if the job reached a terminal state."""
        return self.status in {
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
            JobStatus.EXPIRED.value,
        }

    @classmethod
    def from_row(cls, row: aiosqlite.Row | Mapping[str, Any] | tuple[Any, ...]) -> "Job":
        """Construct a Job instance from an aiosqlite.Row, dict, or tuple.

        Args:
            row: SQLite row object, dict-like mapping, or tuple of column values.

        Returns:
            Job: Instantiated job model.
        """
        if isinstance(row, (dict, aiosqlite.Row)) or hasattr(row, "keys"):
            data = dict(row)
            return cls(
                id=str(data["id"]),
                created_at=str(data["created_at"]),
                updated_at=str(data["updated_at"]),
                source_url_hash=str(data["source_url_hash"]),
                source_host=str(data["source_host"]),
                output_format=str(data["output_format"]),
                output_quality=str(data["output_quality"]),
                expires_at=str(data["expires_at"]),
                status=str(data.get("status", JobStatus.QUEUED.value)),
                progress=float(data["progress"]) if data.get("progress") is not None else None,
                output_filename=(
                    str(data["output_filename"]) if data.get("output_filename") is not None else None
                ),
                output_size=int(data["output_size"]) if data.get("output_size") is not None else None,
                error_code=str(data["error_code"]) if data.get("error_code") is not None else None,
                error_message=(
                    str(data["error_message"]) if data.get("error_message") is not None else None
                ),
                cancelled=int(data.get("cancelled", 0)),
            )

        # Fallback for positional column tuples matching schema order
        row_tuple = tuple(row)
        return cls(
            id=str(row_tuple[0]),
            created_at=str(row_tuple[1]),
            updated_at=str(row_tuple[2]),
            status=str(row_tuple[3]),
            progress=float(row_tuple[4]) if row_tuple[4] is not None else None,
            source_url_hash=str(row_tuple[5]),
            source_host=str(row_tuple[6]),
            output_format=str(row_tuple[7]),
            output_quality=str(row_tuple[8]),
            output_filename=str(row_tuple[9]) if row_tuple[9] is not None else None,
            output_size=int(row_tuple[10]) if row_tuple[10] is not None else None,
            error_code=str(row_tuple[11]) if row_tuple[11] is not None else None,
            error_message=str(row_tuple[12]) if row_tuple[12] is not None else None,
            expires_at=str(row_tuple[13]),
            cancelled=int(row_tuple[14]) if len(row_tuple) > 14 else 0,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the Job dataclass to a dictionary matching database column names.

        Returns:
            dict[str, Any]: Key-value mapping of all database columns.
        """
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "progress": self.progress,
            "source_url_hash": self.source_url_hash,
            "source_host": self.source_host,
            "output_format": self.output_format,
            "output_quality": self.output_quality,
            "output_filename": self.output_filename,
            "output_size": self.output_size,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "expires_at": self.expires_at,
            "cancelled": self.cancelled,
        }
