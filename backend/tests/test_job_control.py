import threading
import time

import pytest

from app.inference import registry
from app.inference.base import AnimationBackend, AnimationRequest, AnimationResult
from app.inference.process import JobCancelled, run_cancellable

from .test_api import _fake_image_bytes, _fake_video_bytes, client  # noqa: F401 - fixture


class SlowBackend(AnimationBackend):
    """Runs a long-lived subprocess so a job stays 'running' until cancelled."""

    name = "slow"
    description = "test-only"

    def is_available(self) -> bool:
        return True

    def run(self, request: AnimationRequest) -> AnimationResult:
        run_cancellable(["sleep", "30"], cancel_event=request.cancel_event)
        raise AssertionError("slow backend should have been cancelled")


class UnavailableBackend(SlowBackend):
    name = "unavailable"

    def is_available(self) -> bool:
        return False


@pytest.fixture()
def test_backends(monkeypatch):
    monkeypatch.setitem(registry._BACKENDS, "slow", SlowBackend)
    monkeypatch.setitem(registry._BACKENDS, "unavailable", UnavailableBackend)


def _submit(client, backend):
    files = {
        "reference_image": ("ref.png", _fake_image_bytes(), "image/png"),
        "driving_video": ("drive.mp4", _fake_video_bytes(), "video/mp4"),
    }
    data = {"backend": backend, "clip_len": "8", "fps": "8", "width": "64", "height": "64"}
    return client.post("/api/jobs", files=files, data=data)


def _wait_for(client, job_id, statuses, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} never reached {statuses}: {job}")


def test_run_cancellable_kills_process():
    event = threading.Event()
    threading.Timer(0.3, event.set).start()
    start = time.time()
    with pytest.raises(JobCancelled):
        run_cancellable(["sleep", "30"], cancel_event=event)
    assert time.time() - start < 5


def test_run_cancellable_returns_output():
    proc = run_cancellable(["sh", "-c", "echo out; echo err >&2; exit 3"])
    assert proc.returncode == 3
    assert proc.stdout.strip() == "out"
    assert proc.stderr.strip() == "err"


def test_rejects_unknown_backend(client):
    resp = _submit(client, "no-such-engine")
    assert resp.status_code == 400
    assert "Unknown" in resp.json()["detail"]


def test_rejects_unavailable_backend(client, test_backends):
    resp = _submit(client, "unavailable")
    assert resp.status_code == 400
    assert "not set up" in resp.json()["detail"]


def test_backends_endpoint_reports_all_engines(client):
    body = client.get("/api/backends").json()
    names = {b["name"] for b in body["backends"]}
    assert {"mock", "tpsmm", "wan-animate-2"} <= names
    assert all(b["description"] for b in body["backends"])
    assert body["default"] == "mock"


def test_cancel_running_and_queued_jobs_then_delete(client, test_backends):
    running = _submit(client, "slow").json()
    _wait_for(client, running["id"], {"running"})

    # The single worker is busy, so this one waits in the queue.
    queued = _submit(client, "mock").json()
    assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "queued"

    resp = client.post(f"/api/jobs/{queued['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    assert client.delete(f"/api/jobs/{running['id']}").status_code == 409

    client.post(f"/api/jobs/{running['id']}/cancel")
    job = _wait_for(client, running["id"], {"cancelled", "failed", "completed"})
    assert job["status"] == "cancelled"

    for job_id in (running["id"], queued["id"]):
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_completed_job_records_engine_log(client):
    job = _submit(client, "mock").json()
    job = _wait_for(client, job["id"], {"completed", "failed"})
    assert job["status"] == "completed", job
    assert "mock backend" in job["log"]


def test_cancel_and_delete_unknown_job_404(client):
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.delete("/api/jobs/nope").status_code == 404


def test_migrates_database_created_before_log_column():
    import sqlite3

    from app.db import _migrate

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL)")
    _migrate(conn)
    _migrate(conn)  # idempotent
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert "log" in columns
