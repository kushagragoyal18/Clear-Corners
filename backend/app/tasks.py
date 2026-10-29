"""Background tasks. Module-level functions with JSON-able args (RQ compatible)."""

from __future__ import annotations

import functools
import logging
from pathlib import Path

import cv2

from .config import settings
from .jobs import FileJobStore
from .video.detection import Box
from .video.ffmpeg_io import VideoInfo, output_container, probe
from .video.pipeline import RenderParams, detect, grab_frame, prepare, render

log = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_store() -> FileJobStore:
    return FileJobStore(settings.data_dir / "jobs")


def _params(raw: dict) -> RenderParams:
    return RenderParams(mode=raw["mode"], box=Box.from_dict(raw["box"]), high_quality=bool(raw.get("high_quality")))


def _task(status: str):
    """Mark the job ``status`` while running and record any failure on the job."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(job_id: str, *args):
            store = get_store()
            store.update(job_id, status=status, progress=0.0, error=None)
            try:
                fn(store, job_id, *args)
            except Exception as e:
                log.exception("%s failed for job %s", fn.__name__, job_id)
                store.update(job_id, status="error", error=str(e)[:500] or type(e).__name__)

        return wrapper

    return deco


def _write_jpg(path: Path, img) -> None:
    if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise RuntimeError(f"could not write {path.name}")


@_task("analyzing")
def run_analyze(store: FileJobStore, job_id: str) -> None:
    job = store.get(job_id)
    d = store.job_dir(job_id)
    src = d / job["input"]

    store.update(job_id, message="Reading video")
    info = probe(src)
    store.update(job_id, info=info.to_dict(), progress=0.2, message="Locating watermark")
    det = detect(src, info)
    _write_jpg(d / "frame.jpg", grab_frame(src, info, info.duration / 2))
    store.update(job_id, status="ready", progress=1.0, message="", detection=det.to_dict(),
                 files={"frame": "frame.jpg"})


@_task("previewing")
def run_preview(store: FileJobStore, job_id: str, raw_params: dict) -> None:
    job = store.get(job_id)
    d = store.job_dir(job_id)
    src, info, params = d / job["input"], VideoInfo.from_dict(job["info"]), _params(raw_params)

    store.update(job_id, message="Estimating watermark model", params=raw_params)
    proc = prepare(src, info, params, cache_dir=d)

    length = min(settings.preview_seconds, info.duration)
    start = max(0.0, info.duration / 2 - length / 2)
    clip = f"preview{output_container(src)}"
    store.update(job_id, message="Rendering 3-second preview")
    # The preview only needs to look right, so encode it with the fastest preset.
    still = render(src, d / clip, info, proc, params.high_quality, start=start, duration=length,
                   progress=lambda p: store.update(job_id, progress=round(p, 3)), preset="ultrafast")
    if still is None:
        raise RuntimeError("preview produced no frames")
    _write_jpg(d / "before.jpg", still[0])
    _write_jpg(d / "after.jpg", still[1])
    store.update(job_id, status="preview_ready", progress=1.0, message="",
                 files={"before": "before.jpg", "after": "after.jpg", "preview": clip})


@_task("rendering")
def run_render(store: FileJobStore, job_id: str, raw_params: dict) -> None:
    job = store.get(job_id)
    d = store.job_dir(job_id)
    src, info, params = d / job["input"], VideoInfo.from_dict(job["info"]), _params(raw_params)

    store.update(job_id, message="Estimating watermark model", params=raw_params)
    proc = prepare(src, info, params, cache_dir=d)
    out = f"output{output_container(src)}"
    store.update(job_id, message="Rendering full video")
    render(src, d / out, info, proc, params.high_quality,
           progress=lambda p: store.update(job_id, progress=round(p, 3)))
    store.update(job_id, status="done", progress=1.0, message="", files={"output": out})
