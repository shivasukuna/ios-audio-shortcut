"""Pydantic v2 schemas and models for audio downloader requests and responses."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    model_validator,
)


class AudioFormat(str, Enum):
    """Supported output audio file formats."""

    MP3 = "mp3"
    AAC = "aac"
    OPUS = "opus"
    M4A = "m4a"


class AudioQuality(str, Enum):
    """Supported output audio bitrates and quality levels."""

    Q128K = "128k"
    Q192K = "192k"
    Q320K = "320k"
    BEST = "best"


class JobCreateRequest(BaseModel):
    """Payload to initiate a new audio extraction job."""

    url: HttpUrl | str = Field(
        ...,
        description="Public URL of the media video/post to extract audio from.",
    )
    format: AudioFormat = Field(
        default=AudioFormat.MP3,
        description="Target audio container format.",
    )
    quality: AudioQuality = Field(
        default=AudioQuality.Q192K,
        description="Target audio bitrate or quality preset.",
    )

    @model_validator(mode="after")
    def convert_url_to_string(self) -> "JobCreateRequest":
        """Validate URL structure and guarantee the url attribute is stored as str."""
        if isinstance(self.url, HttpUrl):
            self.url = str(self.url)
        elif isinstance(self.url, str):
            validated_url = TypeAdapter(HttpUrl).validate_python(self.url)
            self.url = str(validated_url)
        return self


class JobCreateResponse(BaseModel):
    """Response returned when a download job is successfully submitted."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    job_id: str = Field(
        ...,
        validation_alias=AliasChoices("job_id", "id"),
        description="Unique identifier assigned to the job.",
    )
    status: str = Field(
        ...,
        description="Initial job status (typically 'queued').",
    )
    status_url: str = Field(
        ...,
        description="Relative endpoint URL to poll for job progress and status.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when the job was accepted.",
    )


class JobStatusResponse(BaseModel):
    """Status details for a query on an existing job."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    job_id: str = Field(
        ...,
        validation_alias=AliasChoices("job_id", "id"),
        description="Unique identifier of the job.",
    )
    status: str = Field(
        ...,
        description="Current state of the job (e.g. queued, processing, completed, failed).",
    )
    progress: float | None = Field(
        default=None,
        description="Download/conversion progress percentage (0.0 to 100.0).",
    )
    output_filename: str | None = Field(
        default=None,
        description="Name of the generated audio file on completion.",
    )
    output_size: int | None = Field(
        default=None,
        description="File size in bytes of the extracted audio artifact.",
    )
    error_code: str | None = Field(
        default=None,
        description="Standardized machine-readable error code if failed.",
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable explanation of error or failure reason.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp of creation.",
    )
    updated_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp of last status update.",
    )
    expires_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp after which the job artifact will be purged.",
    )


class FileTokenResponse(BaseModel):
    """Signed single-use or time-bound download URL response."""

    download_url: str = Field(
        ...,
        description="Direct download URL containing signed access token.",
    )
    expires_in: int = Field(
        ...,
        description="Token lifetime in seconds until expiration.",
    )


class ErrorResponse(BaseModel):
    """Standardized error response payload."""

    error: str = Field(
        ...,
        description="Short error classification.",
    )
    detail: str = Field(
        ...,
        description="Descriptive explanation of the error.",
    )
    code: str = Field(
        ...,
        description="Machine-readable error identifier.",
    )


class HealthResponse(BaseModel):
    """Lightweight readiness and liveness probe response."""

    status: str = Field(
        default="ok",
        description="Health status indicator.",
    )
    version: str = Field(
        default="0.1.0",
        description="Application version.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Current UTC timestamp.",
    )


class ComponentStatus(BaseModel):
    """Health indicator for an individual subsystem."""

    status: str = Field(
        ...,
        description="Subsystem health status ('ok', 'warning', or 'error').",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic metadata and metrics for the subsystem.",
    )


class DeepHealthResponse(BaseModel):
    """Detailed health check inspects database, disk space, and worker queue."""

    status: str = Field(
        default="ok",
        description="Overall composite system health status.",
    )
    version: str = Field(
        default="0.1.0",
        description="Application version.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Current UTC timestamp.",
    )
    database: ComponentStatus = Field(
        ...,
        description="Database connectivity and latency status.",
    )
    disk: ComponentStatus = Field(
        ...,
        description="Storage disk capacity and usage status.",
    )
    queue: ComponentStatus = Field(
        ...,
        description="Job queue backlog and worker status.",
    )
    yt_dlp_version: str = Field(
        ...,
        description="Version string of the installed yt-dlp binary or library.",
    )


class LimitsResponse(BaseModel):
    """Configurable system constraints and media extraction limits."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    max_concurrent_jobs: int = Field(
        ...,
        validation_alias=AliasChoices("max_concurrent_jobs", "MAX_CONCURRENT_JOBS"),
        description="Maximum concurrent downloads processed simultaneously.",
    )
    max_queue_size: int = Field(
        ...,
        validation_alias=AliasChoices("max_queue_size", "MAX_QUEUE_SIZE"),
        description="Maximum number of waiting jobs accepted in queue.",
    )
    max_file_size_mb: int = Field(
        ...,
        validation_alias=AliasChoices("max_file_size_mb", "MAX_FILE_SIZE_MB"),
        description="Maximum allowed media file size in megabytes.",
    )
    max_duration_seconds: int = Field(
        ...,
        validation_alias=AliasChoices("max_duration_seconds", "MAX_DURATION_SECONDS"),
        description="Maximum allowed media duration in seconds.",
    )
    max_playlist_length: int = Field(
        ...,
        validation_alias=AliasChoices("max_playlist_length", "MAX_PLAYLIST_LENGTH"),
        description="Maximum number of items permitted if URL resolves to a playlist.",
    )
    job_timeout_seconds: int = Field(
        ...,
        validation_alias=AliasChoices("job_timeout_seconds", "JOB_TIMEOUT_SECONDS"),
        description="Maximum execution timeout before a job is aborted.",
    )
    artifact_ttl_seconds: int = Field(
        ...,
        validation_alias=AliasChoices("artifact_ttl_seconds", "ARTIFACT_TTL_SECONDS"),
        description="Retention lifetime of completed audio files in seconds.",
    )
    download_token_ttl_seconds: int = Field(
        ...,
        validation_alias=AliasChoices("download_token_ttl_seconds", "DOWNLOAD_TOKEN_TTL_SECONDS"),
        description="Validity window of signed download tokens in seconds.",
    )
    rate_limit_requests: int = Field(
        ...,
        validation_alias=AliasChoices("rate_limit_requests", "RATE_LIMIT_REQUESTS"),
        description="Allowed request count within the rate limit window.",
    )
    rate_limit_window_seconds: int = Field(
        ...,
        validation_alias=AliasChoices("rate_limit_window_seconds", "RATE_LIMIT_WINDOW_SECONDS"),
        description="Duration of the rate limit window in seconds.",
    )
    supported_formats: list[str] = Field(
        ...,
        validation_alias=AliasChoices("supported_formats", "SUPPORTED_FORMATS"),
        description="List of supported audio container format strings.",
    )
    supported_qualities: list[str] = Field(
        ...,
        validation_alias=AliasChoices("supported_qualities", "SUPPORTED_QUALITIES"),
        description="List of supported audio quality/bitrate presets.",
    )
    allowed_hosts: list[str] = Field(
        ...,
        validation_alias=AliasChoices("allowed_hosts", "ALLOWED_HOSTS"),
        description="List of permitted video platform hostnames.",
    )
