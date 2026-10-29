"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_list(name: str, default: str) -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


def _origins(name: str, default: str) -> list[str]:
    # Browsers send the Origin header without a trailing slash, so a URL pasted
    # as "https://site.app/" would never match; normalise it.
    return [o.rstrip("/") for o in _env_list(name, default)]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).resolve()
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024
    job_ttl_seconds: int = int(os.getenv("JOB_TTL_SECONDS", "3600"))
    cleanup_interval_seconds: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))
    workers: int = int(os.getenv("WORKERS", "2"))
    preview_seconds: float = float(os.getenv("PREVIEW_SECONDS", "3"))
    cors_origins: list[str] = field(default_factory=lambda: _origins("CORS_ORIGINS", "http://localhost:3000"))
    # Optional regex for origins that change per deploy, e.g. Vercel previews:
    #   CORS_ORIGIN_REGEX=https://clean-corners(-[a-z0-9-]+)?\.vercel\.app
    cors_origin_regex: str | None = os.getenv("CORS_ORIGIN_REGEX") or None
    allowed_extensions: tuple[str, ...] = (".mp4", ".mov", ".webm")


settings = Settings()
