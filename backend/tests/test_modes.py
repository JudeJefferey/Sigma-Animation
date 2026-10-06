"""Animate-image (image + prompt) and reanimate-video modes."""
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.inference import registry
from app.inference.base import AnimationBackend, AnimationRequest, AnimationResult
from app.inference.wan_ti2v import WanTI2VBackend

from .test_api import _fake_image_bytes, client  # noqa: F401 - fixture
from .test_job_control import _wait_for, test_backends  # noqa: F401 - fixture


def _real_video_bytes(tmp_path: Path, seconds: int = 1) -> bytes:
    path = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x64:rate=8",
         "-t", str(seconds), str(path)],
        check=True,
    )
    return path.read_bytes()


class MotionOnlyBackend(AnimationBackend):
    name = "motion-only"
    max_clip_seconds = 5

    def is_available(self) -> bool:
        return True

    def run(self, request: AnimationRequest) -> AnimationResult:
        raise AssertionError("not expected to run")


@pytest.fixture()
def motion_only(monkeypatch):
    monkeypatch.setitem(registry._BACKENDS, "motion-only", MotionOnlyBackend)


SETTINGS = {"backend": "mock", "clip_len": "8", "fps": "8", "width": "64", "height": "64"}


def _image():
    return ("ref.png", _fake_image_bytes(), "image/png")


def _video(tmp_path, name="drive.mp4"):
    return (name, _real_video_bytes(tmp_path), "video/mp4")


def _completed(client, resp):
    assert resp.status_code == 200, resp.text
    job = _wait_for(client, resp.json()["id"], {"completed", "failed"}, timeout=30)
    assert job["status"] == "completed", job
    return job


# --- animate image (image + prompt) ---------------------------------------


def test_animate_image_with_prompt(client):
    resp = client.post(
        "/api/jobs",
        files={"reference_image": _image()},
        data={**SETTINGS, "mode": "image_to_video", "prompt": "the cat waves"},
    )
    job = _completed(client, resp)
    assert job["params"]["mode"] == "image_to_video"
    assert job["params"]["prompt"] == "the cat waves"


def test_animate_image_needs_prompt(client):
    resp = client.post("/api/jobs", files={"reference_image": _image()}, data={**SETTINGS, "mode": "image_to_video"})
    assert resp.status_code == 400
    assert "prompt" in resp.json()["detail"]


def test_animate_image_rejects_motion_only_engine(client, motion_only):
    resp = client.post(
        "/api/jobs",
        files={"reference_image": _image()},
        data={**SETTINGS, "mode": "image_to_video", "prompt": "waves", "backend": "motion-only"},
    )
    assert resp.status_code == 400
    assert "can't do image to video" in resp.json()["detail"]


def test_engine_clip_limit_applies(client, motion_only, tmp_path):
    resp = client.post(
        "/api/jobs",
        files={"reference_image": _image(), "driving_video": _video(tmp_path)},
        data={**SETTINGS, "backend": "motion-only", "clip_len": "48", "fps": "8"},
    )
    assert resp.status_code == 400
    assert "maximum is 5s" in resp.json()["detail"]


def test_motion_transfer_needs_driving_video(client):
    resp = client.post("/api/jobs", files={"reference_image": _image()}, data=SETTINGS)
    assert resp.status_code == 400


def test_unknown_mode(client):
    resp = client.post("/api/jobs", files={"reference_image": _image()}, data={**SETTINGS, "mode": "dance"})
    assert resp.status_code == 400


# --- reanimate ----------------------------------------------------------------


def test_reanimate_uploaded_video(client, tmp_path):
    resp = client.post(
        "/api/jobs",
        files={"source_video": _video(tmp_path, "source.mp4"), "driving_video": _video(tmp_path)},
        data={**SETTINGS, "mode": "reanimate"},
    )
    job = _completed(client, resp)
    assert job["params"]["mode"] == "reanimate"
    assert job["params"]["source_job_id"] is None
    frame = settings.uploads_dir / job["id"] / "image.png"
    assert frame.is_file() and frame.stat().st_size > 0


def test_reanimate_previous_result_with_new_motion(client, tmp_path):
    first = _completed(client, client.post(
        "/api/jobs", files={"reference_image": _image(), "driving_video": _video(tmp_path)}, data=SETTINGS,
    ))
    resp = client.post(
        "/api/jobs",
        files={"driving_video": _video(tmp_path)},
        data={**SETTINGS, "mode": "reanimate", "source_job_id": first["id"]},
    )
    job = _completed(client, resp)
    assert job["params"]["mode"] == "reanimate"
    assert job["params"]["source_job_id"] == first["id"]


def test_rerun_previous_result_with_new_settings(client):
    first = _completed(client, client.post(
        "/api/jobs",
        files={"reference_image": _image()},
        data={**SETTINGS, "mode": "image_to_video", "prompt": "the cat waves"},
    ))
    # No driving video: re-run the original inputs (image + prompt) at new settings.
    resp = client.post(
        "/api/jobs",
        data={**SETTINGS, "mode": "reanimate", "source_job_id": first["id"], "fps": "4", "clip_len": "8"},
    )
    job = _completed(client, resp)
    assert job["params"]["mode"] == "image_to_video"
    assert job["params"]["prompt"] == "the cat waves"
    assert job["params"]["fps"] == 4
    assert job["params"]["source_job_id"] == first["id"]

    # The re-run has its own copies of the inputs.
    assert client.delete(f"/api/jobs/{first['id']}").status_code == 204
    assert any((settings.uploads_dir / job["id"]).iterdir())


@pytest.mark.parametrize("case", ["both_sources", "no_source", "upload_without_motion"])
def test_reanimate_rejects_bad_inputs(client, tmp_path, case):
    files = {
        "both_sources": {"source_video": _video(tmp_path, "s.mp4"), "driving_video": _video(tmp_path)},
        "no_source": {"driving_video": _video(tmp_path)},
        "upload_without_motion": {"source_video": _video(tmp_path, "s.mp4")},
    }[case]
    data = {**SETTINGS, "mode": "reanimate"}
    if case == "both_sources":
        data["source_job_id"] = "whatever"
    resp = client.post("/api/jobs", files=files, data=data)
    assert resp.status_code == 400, resp.text


def test_reanimate_unknown_or_unfinished_source(client, test_backends, tmp_path):
    assert client.post(
        "/api/jobs", data={**SETTINGS, "mode": "reanimate", "source_job_id": "nope"},
    ).status_code == 404

    running = client.post(
        "/api/jobs", files={"reference_image": _image(), "driving_video": _video(tmp_path)},
        data={**SETTINGS, "backend": "slow"},
    ).json()
    resp = client.post("/api/jobs", data={**SETTINGS, "mode": "reanimate", "source_job_id": running["id"]})
    assert resp.status_code == 400
    client.post(f"/api/jobs/{running['id']}/cancel")
    _wait_for(client, running["id"], {"cancelled"})


def test_reanimate_rejects_non_video_source(client, tmp_path):
    resp = client.post(
        "/api/jobs",
        files={"source_video": ("s.mp4", b"not a video", "video/mp4"), "driving_video": _video(tmp_path)},
        data={**SETTINGS, "mode": "reanimate"},
    )
    assert resp.status_code == 400
    assert "frame" in resp.json()["detail"]


# --- Wan2.2 TI2V adapter --------------------------------------------------------


@pytest.mark.parametrize(
    ("clip_len", "fps", "expected"),
    [(120, 24, 121), (72, 24, 73), (24, 24, 25), (8, 8, 25), (1, 24, 5), (600, 24, 121)],
)
def test_ti2v_frame_num_is_4n_plus_1_and_capped(clip_len, fps, expected):
    assert WanTI2VBackend.frame_num(clip_len, fps) == expected


FAKE_GENERATE = """
import argparse, json, subprocess
p = argparse.ArgumentParser()
for a in ["--task", "--size", "--ckpt_dir", "--image", "--prompt", "--frame_num",
          "--sample_steps", "--base_seed", "--save_file", "--offload_model"]:
    p.add_argument(a)
p.add_argument("--convert_model_dtype", action="store_true")
p.add_argument("--t5_cpu", action="store_true")
args = p.parse_args()
json.dump(vars(args), open("args.json", "w"))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", args.image, "-t", "1",
                "-vf", "scale=128:72,fps=24", "-pix_fmt", "yuv420p", args.save_file], check=True)
"""


def test_ti2v_adapter_runs_generate_py(tmp_path, monkeypatch):
    import json

    from PIL import Image

    repo = tmp_path / "Wan2.2"
    (repo / "Wan2.2-TI2V-5B").mkdir(parents=True)
    (repo / "generate.py").write_text(FAKE_GENERATE)
    monkeypatch.setattr(settings, "wan_ti2v_repo", str(repo))
    monkeypatch.setattr(settings, "wan_ti2v_python", sys.executable)

    image = tmp_path / "ref.png"
    Image.new("RGB", (64, 64), (10, 200, 10)).save(image)
    backend = WanTI2VBackend()
    assert backend.is_available()

    result = backend.run(AnimationRequest(
        reference_image_path=image, driving_video_path=None, output_dir=tmp_path / "out",
        width=320, height=180, fps=12, clip_len=24, steps=30, seed=7, prompt="it spins",
    ))
    args = json.loads((repo / "args.json").read_text())
    assert args["task"] == "ti2v-5B"
    assert args["size"] == "1280*704"
    assert args["prompt"] == "it spins"
    assert args["frame_num"] == "49"
    assert args["sample_steps"] == "30" and args["base_seed"] == "7"
    assert args["offload_model"] == "True" and args["t5_cpu"]

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "csv=p=0", str(result.output_video_path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert probe == "320,180,12/1"


def test_ti2v_unavailable_without_weights(tmp_path, monkeypatch):
    (tmp_path / "generate.py").write_text("")
    monkeypatch.setattr(settings, "wan_ti2v_repo", str(tmp_path))
    assert WanTI2VBackend().is_available() is False
