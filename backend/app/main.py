"""HTTP API.

POST /api/jobs                 upload a video -> job id (analysis starts automatically)
GET  /api/jobs/{id}            job status, progress, detection, file names
POST /api/jobs/{id}/preview    before/after still + 3 s clip for {mode, box, high_quality}
POST /api/jobs/{id}/render     full render with the same params
GET  /api/jobs/{id}/files/{k}  frame | before | after | preview | output
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import settings
from .jobs import BUSY, Cleaner, InProcessQueue, TaskQueue
from .tasks import get_store
from .video.pipeline import MODES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

queue: TaskQueue = InProcessQueue(settings.workers)


@asynccontextmanager
async def lifespan(_: FastAPI):
    cleaner = Cleaner(get_store(), settings.job_ttl_seconds, settings.cleanup_interval_seconds)
    cleaner.start()
    yield
    cleaner.stop()
    if isinstance(queue, InProcessQueue):
        queue.shutdown()


app = FastAPI(title="Watermark Remover", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])


class BoxIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class ParamsIn(BaseModel):
    mode: str = "alpha"
    box: BoxIn
    high_quality: bool = False


def _job_or_404(job_id: str) -> dict:
    job = get_store().get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found or expired")
    return job


def _public(job: dict) -> dict:
    keys = ("id", "status", "progress", "message", "error", "info", "detection", "params", "created_at")
    out = {k: job.get(k) for k in keys}
    out["files"] = sorted(job.get("files", {}))
    out["expires_at"] = job["created_at"] + settings.job_ttl_seconds
    return out


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/jobs", status_code=201)
async def create_job(request: Request, file: UploadFile = File(...)) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(415, f"Unsupported file type. Use {', '.join(settings.allowed_extensions)}")
    declared = int(request.headers.get("content-length") or 0)
    if declared > settings.max_upload_bytes + 1024 * 1024:  # allow multipart overhead
        raise HTTPException(413, "File is larger than 200 MB")

    store = get_store()
    job = store.create(input=f"input{ext}", original_name=Path(file.filename).name)
    dest = store.job_dir(job["id"]) / job["input"]
    size = 0
    with dest.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                fh.close()
                store.delete(job["id"])
                raise HTTPException(413, "File is larger than 200 MB")
            fh.write(chunk)

    store.update(job["id"], status="queued", size=size)
    queue.enqueue("app.tasks.run_analyze", job["id"])
    return _public(store.get(job["id"]))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _public(_job_or_404(job_id))


def _start(job_id: str, params: ParamsIn, task: str) -> dict:
    job = _job_or_404(job_id)
    if job["status"] in BUSY:
        raise HTTPException(409, "A task is already running for this job")
    if not job.get("info"):
        raise HTTPException(409, "Video has not been analysed yet")
    if params.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {MODES}")
    info = job["info"]
    b = params.box
    if b.x + b.w > info["width"] or b.y + b.h > info["height"]:
        raise HTTPException(422, "Box lies outside the frame")
    store = get_store()
    store.update(job_id, status="queued", progress=0.0, message="Queued")
    queue.enqueue(task, job_id, params.model_dump())
    return _public(store.get(job_id))


@app.post("/api/jobs/{job_id}/preview")
def start_preview(job_id: str, params: ParamsIn) -> dict:
    return _start(job_id, params, "app.tasks.run_preview")


@app.post("/api/jobs/{job_id}/render")
def start_render(job_id: str, params: ParamsIn) -> dict:
    return _start(job_id, params, "app.tasks.run_render")


MEDIA_TYPES = {".jpg": "image/jpeg", ".mp4": "video/mp4", ".mov": "video/quicktime"}


@app.get("/api/jobs/{job_id}/files/{key}")
def get_file(job_id: str, key: str) -> FileResponse:
    job = _job_or_404(job_id)
    name = job.get("files", {}).get(key)
    if not name:
        raise HTTPException(404, "File not available")
    path = get_store().job_dir(job_id) / name
    if not path.exists():
        raise HTTPException(404, "File expired")
    kwargs = {}
    if key == "output":
        stem = Path(job.get("original_name") or "video").stem
        kwargs["filename"] = f"{stem}_clean{path.suffix}"
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix, "application/octet-stream"), **kwargs)
