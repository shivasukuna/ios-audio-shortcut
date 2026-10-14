"""Application configuration module.

Loads environment variables using Pydantic Settings v2, provides type validation,
sensible defaults, and derives cryptographic secrets when needed.
"""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required Authentication
    API_TOKEN: str

    # Worker Concurrency and Queue
    MAX_CONCURRENT_JOBS: int = 2
    MAX_QUEUE_SIZE: int = 10

    # Media Limits
    MAX_FILE_SIZE_MB: int = 100
    MAX_DURATION_SECONDS: int = 1800
    MAX_PLAYLIST_LENGTH: int = 1

    # Job Lifecycle
    JOB_TIMEOUT_SECONDS: int = 600
    ARTIFACT_TTL_SECONDS: int = 3600
    DOWNLOAD_TOKEN_TTL_SECONDS: int = 300

    # Storage Paths
    OUTPUT_DIR: str = "/data/output"
    TEMP_DIR: str = "/data/tmp"
    DB_PATH: str = "/data/db/jobs.db"

    # Disk Resource Monitoring
    DISK_WARNING_PERCENT: int = 80
    DISK_REJECT_PERCENT: int = 90

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Server and Logging Configuration
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Allowed Host Domains for Audio Extraction (Instagram only)
    ALLOWED_HOSTS: list[str] = Field(
        default_factory=lambda: [
            "instagram.com",
            "www.instagram.com",
        ]
    )

    # Supported Formats and Qualities
    SUPPORTED_FORMATS: list[str] = Field(
        default_factory=lambda: ["mp3", "aac", "opus", "m4a"]
    )
    SUPPORTED_QUALITIES: list[str] = Field(
        default_factory=lambda: ["128k", "192k", "320k", "best"]
    )

    # HMAC Secret for One-Time Download Token Signing
    HMAC_SECRET: str = ""

    @field_validator(
        "ALLOWED_HOSTS",
        "SUPPORTED_FORMATS",
        "SUPPORTED_QUALITIES",
        mode="before",
    )
    @classmethod
    def parse_comma_or_json_list(cls, value: Any) -> list[str]:
        """Parse string-encoded lists from environment variables or .env file."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in stripped.split(",") if part.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @model_validator(mode="after")
    def derive_hmac_secret(self) -> "Settings":
        """Derive HMAC_SECRET from API_TOKEN using SHA-256 if not explicitly provided."""
        if not self.HMAC_SECRET:
            derived = hashlib.sha256(self.API_TOKEN.encode("utf-8")).hexdigest()
            self.HMAC_SECRET = derived
        return self

    @property
    def hmac_secret(self) -> str:
        """Return HMAC_SECRET string."""
        return self.HMAC_SECRET

    @property
    def output_dir_path(self) -> Path:
        """Return OUTPUT_DIR as a Path object."""
        return Path(self.OUTPUT_DIR)

    @property
    def temp_dir_path(self) -> Path:
        """Return TEMP_DIR as a Path object."""
        return Path(self.TEMP_DIR)

    @property
    def db_path_path(self) -> Path:
        """Return DB_PATH as a Path object."""
        return Path(self.DB_PATH)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton instance of the application settings."""
    return Settings()
