"""Job state and the task queue.

Both are behind small interfaces so the in-process implementations can be
swapped for Redis/RQ later without touching the API or the tasks:

* ``JobStore`` persists job records. ``FileJobStore`` writes one JSON file per
  job inside the job's directory, so a separate worker process sharing the
  data volume can already read and update it.
* ``TaskQueue`` runs a task by *import path + JSON-able args*. That is exactly
  the shape ``rq.Queue.enqueue("app.tasks.run_render", job_id, params)`` wants.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Statuses during which a task is running and another must not be started.
BUSY = {"queued", "analyzing", "previewing", "rendering"}


class JobStore(Protocol):
    def create(self, **fields: Any) -> dict: ...
    def get(self, job_id: str) -> dict | None: ...
    def update(self, job_id: str, **fields: Any) -> dict: ...
    def job_dir(self, job_id: str) -> Path: ...
    def delete(self, job_id: str) -> None: ...
    def purge_older_than(self, seconds: float) -> int: ...


class FileJobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def job_dir(self, job_id: str) -> Path:
        # Job ids are uuid4 hex; reject anything else to avoid path traversal.
        if not (len(job_id) == 32 and all(c in "0123456789abcdef" for c in job_id)):
            raise KeyError(job_id)
        return self.root / job_id

    def _path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def _write(self, job: dict) -> None:
        path = self._path(job["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, indent=2))
        os.replace(tmp, path)

    def create(self, **fields: Any) -> dict:
        job_id = uuid.uuid4().hex
        self.job_dir(job_id).mkdir(parents=True)
        now = time.time()
        job = {"id": job_id, "status": "created", "progress": 0.0, "message": "", "error": None,
               "created_at": now, "updated_at": now, "files": {}, **fields}
        with self._lock:
            self._write(job)
        return job

    def get(self, job_id: str) -> dict | None:
        try:
            return json.loads(self._path(job_id).read_text())
        except (KeyError, FileNotFoundError, json.JSONDecodeError):
            return None

    def update(self, job_id: str, **fields: Any) -> dict:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                raise KeyError(job_id)
            files = fields.pop("files", None)
            job.update(fields)
            if files:
                job["files"] = {**job.get("files", {}), **files}
            job["updated_at"] = time.time()
            self._write(job)
            return job

    def delete(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def purge_older_than(self, seconds: float) -> int:
        """Delete job directories (uploads, previews, outputs) past their TTL."""
        cutoff = time.time() - seconds
        removed = 0
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            job = self.get(d.name) if len(d.name) == 32 else None
            created = job["created_at"] if job else d.stat().st_mtime
            if created < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed


class TaskQueue(Protocol):
    def enqueue(self, func_path: str, *args: Any) -> None: ...


def _resolve(func_path: str):
    module, _, name = func_path.rpartition(".")
    return getattr(importlib.import_module(module), name)


class InProcessQueue:
    """Thread-pool queue. Video work is mostly in OpenCV/ffmpeg, which release the GIL."""

    def __init__(self, workers: int):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")

    def enqueue(self, func_path: str, *args: Any) -> None:
        func = _resolve(func_path)

        def run():
            try:
                func(*args)
            except Exception:  # tasks record their own errors; this is a last resort
                log.exception("task %s failed", func_path)

        self._pool.submit(run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class Cleaner(threading.Thread):
    """Background thread that enforces the job TTL."""

    def __init__(self, store: JobStore, ttl: float, interval: float):
        super().__init__(daemon=True, name="cleaner")
        self.store, self.ttl, self.interval = store, ttl, interval
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                n = self.store.purge_older_than(self.ttl)
                if n:
                    log.info("cleanup removed %d expired job(s)", n)
            except Exception:
                log.exception("cleanup failed")
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()
