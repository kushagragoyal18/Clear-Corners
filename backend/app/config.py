"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_list(name: str, default: str) -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).resolve()
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024
    job_ttl_seconds: int = int(os.getenv("JOB_TTL_SECONDS", "3600"))
    cleanup_interval_seconds: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))
    workers: int = int(os.getenv("WORKERS", "2"))
    preview_seconds: float = float(os.getenv("PREVIEW_SECONDS", "3"))
    cors_origins: list[str] = field(default_factory=lambda: _env_list("CORS_ORIGINS", "http://localhost:3000"))
    allowed_extensions: tuple[str, ...] = (".mp4", ".mov", ".webm")


settings = Settings()
