import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SIGMA_DB_PATH", str(tmp_path / "data" / "sigma.db"))

    from app.main import app

    with TestClient(app) as c:
        yield c


def _fake_image_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(120, 60, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _fake_video_bytes() -> bytes:
    # Not a real video; the mock backend only reads the reference image.
    return b"fake video bytes"


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_backends_endpoint_lists_mock(client):
    resp = client.get("/api/backends")
    assert resp.status_code == 200
    assert "mock" in resp.json()["available"]


def test_full_job_lifecycle_with_mock_backend(client):
    files = {
        "reference_image": ("ref.png", _fake_image_bytes(), "image/png"),
        "driving_video": ("drive.mp4", _fake_video_bytes(), "video/mp4"),
    }
    data = {"backend": "mock", "clip_len": "24", "fps": "8", "width": "64", "height": "64"}

    resp = client.post("/api/jobs", files=files, data=data)
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] in ("queued", "running", "completed")
    job_id = job["id"]

    deadline = time.time() + 30
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        job = resp.json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)

    assert job["status"] == "completed", job
    assert job["output_video_url"] == f"/api/jobs/{job_id}/result"

    result_resp = client.get(job["output_video_url"])
    assert result_resp.status_code == 200
    assert result_resp.headers["content-type"] == "video/mp4"
    assert len(result_resp.content) > 0


def test_rejects_unsupported_file_type(client):
    files = {
        "reference_image": ("ref.txt", b"not an image", "text/plain"),
        "driving_video": ("drive.mp4", _fake_video_bytes(), "video/mp4"),
    }
    resp = client.post("/api/jobs", files=files, data={"backend": "mock"})
    assert resp.status_code == 400


def test_unknown_job_returns_404(client):
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404
