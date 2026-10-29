"""API validation and job lifecycle, with the task queue stubbed out (no ffmpeg needed)."""

import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.tasks import get_store


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, func_path, *args):
        self.calls.append((func_path, args))


@pytest.fixture
def client(monkeypatch):
    q = FakeQueue()
    monkeypatch.setattr(main, "queue", q)
    with TestClient(main.app) as c:
        c.queue = q
        yield c


def test_rejects_unsupported_extension(client):
    r = client.post("/api/jobs", files={"file": ("clip.avi", b"x" * 10, "video/x-msvideo")})
    assert r.status_code == 415


def test_rejects_oversized_upload(client):
    r = client.post("/api/jobs", files={"file": ("clip.mp4", b"x" * (2 * 1024 * 1024), "video/mp4")})
    assert r.status_code == 413


def test_upload_enqueues_analysis_and_reports_status(client):
    r = client.post("/api/jobs", files={"file": ("clip.mp4", b"fake", "video/mp4")})
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "queued"
    assert client.queue.calls == [("app.tasks.run_analyze", (job["id"],))]
    assert client.get(f"/api/jobs/{job['id']}").json()["id"] == job["id"]


def test_preview_validates_box_and_mode(client):
    job = client.post("/api/jobs", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()
    store = get_store()
    store.update(job["id"], status="ready", info={"width": 640, "height": 360})

    body = {"mode": "alpha", "box": {"x": 600, "y": 300, "w": 100, "h": 40}}
    assert client.post(f"/api/jobs/{job['id']}/preview", json=body).status_code == 422  # off-frame
    body["box"] = {"x": 500, "y": 300, "w": 100, "h": 40}
    body["mode"] = "magic"
    assert client.post(f"/api/jobs/{job['id']}/preview", json=body).status_code == 422
    body["mode"] = "inpaint_temporal"
    r = client.post(f"/api/jobs/{job['id']}/preview", json=body)
    assert r.status_code == 200
    # A second task while the first is queued is refused.
    assert client.post(f"/api/jobs/{job['id']}/render", json=body).status_code == 409


def test_unknown_and_malformed_job_ids(client):
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    assert client.get("/api/jobs/..%2F..%2Fetc").status_code == 404


def test_expired_jobs_are_purged():
    store = get_store()
    job = store.create(input="input.mp4")
    store.update(job["id"], created_at=time.time() - 7200)
    assert store.purge_older_than(3600) >= 1
    assert store.get(job["id"]) is None
