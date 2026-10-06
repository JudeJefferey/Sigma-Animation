from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .. import jobs as jobs_service
from ..config import settings
from ..inference.registry import available_backends, backend_info
from ..inference.video import extract_first_frame
from ..models import ENGINE_MODE, JobOut, JobParams
from ..storage import copy_input, job_upload_dir, new_job_id, save_upload

router = APIRouter(prefix="/api", tags=["animation"])


def _to_job_out(job: dict) -> JobOut:
    output_url = f"/api/jobs/{job['id']}/result" if job["output_video_path"] else None
    return JobOut(
        id=job["id"],
        status=job["status"],
        backend=job["backend"],
        params=JobParams(**job["params"]),
        output_video_url=output_url,
        error=job["error"],
        log=job.get("log"),
        processing_seconds=job["processing_seconds"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@router.get("/backends")
def list_backends() -> dict:
    backends = backend_info()
    return {
        "available": [b["name"] for b in backends if b["available"]],
        "default": settings.default_backend,
        "backends": backends,
    }


def _validate_clip(clip_len: int, fps: int, max_seconds: int) -> None:
    if fps < 1:
        raise HTTPException(status_code=400, detail="fps must be at least 1")
    if clip_len < 1:
        raise HTTPException(status_code=400, detail="clip_len must be at least 1 frame")
    if clip_len / fps > max_seconds:
        raise HTTPException(
            status_code=400,
            detail=f"Clip is too long: {clip_len} frames at {fps}fps is {clip_len / fps:.1f}s; "
            f"the maximum is {max_seconds}s",
        )


def _validate_output_fps(output_fps: int, fps: int) -> None:
    if output_fps == 0:
        return
    if not fps <= output_fps <= settings.max_output_fps:
        raise HTTPException(
            status_code=400,
            detail=f"output_fps must be 0 (off) or between the generation fps ({fps}) "
            f"and {settings.max_output_fps}",
        )


def _require_usable_backend(name: str, engine_mode: str) -> dict:
    known = {b["name"]: b for b in backend_info()}
    if name not in known:
        raise HTTPException(status_code=400, detail=f"Unknown animation backend '{name}'. Known: {sorted(known)}")
    info = known[name]
    if not info["available"]:
        raise HTTPException(
            status_code=400,
            detail=f"Animation backend '{name}' is not set up on this server (see docs/MODEL_SETUP.md). "
            f"Available: {available_backends()}",
        )
    if engine_mode not in info["modes"]:
        capable = [b["name"] for b in known.values() if engine_mode in b["modes"]]
        raise HTTPException(
            status_code=400,
            detail=f"Animation backend '{name}' can't do {engine_mode.replace('_', ' ')}. Engines that can: {capable}",
        )
    return info


def _present(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


def _completed_source_job(source_job_id: str) -> dict:
    job = jobs_service.get_job(source_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Source job '{source_job_id}' not found")
    if job["status"] != "completed" or not job["output_video_path"] or not Path(job["output_video_path"]).is_file():
        raise HTTPException(status_code=400, detail="Source job has no finished video to reanimate")
    return job


@router.post("/jobs", response_model=JobOut)
async def create_job(
    mode: str = Form("motion_transfer"),
    reference_image: UploadFile | None = File(None),
    driving_video: UploadFile | None = File(None),
    source_video: UploadFile | None = File(None),
    source_job_id: str | None = Form(None),
    backend: str | None = Form(None),
    prompt: str = Form(""),
    prompt_ref: str = Form("reference video of the character's motion"),
    width: int = Form(720),
    height: int = Form(1280),
    fps: int = Form(24),
    output_fps: int = Form(0),
    clip_len: int = Form(81),
    sample_guide_scale: float = Form(3.0),
    steps: int = Form(40),
    seed: int = Form(-1),
) -> JobOut:
    """Submit a job in one of three modes.

    - motion_transfer: `reference_image` follows the motion in `driving_video`.
    - image_to_video: `reference_image` is animated from `prompt`; no video.
    - reanimate: the source -- an uploaded `source_video`, or the result of
      `source_job_id` -- gets new motion from `driving_video`, using the source's
      first frame as the character. With `source_job_id` and no
      `driving_video`, the earlier job is re-run from its original inputs with
      the new settings instead.
    """
    if mode not in ENGINE_MODE:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'. Modes: {sorted(ENGINE_MODE)}")

    # Work out what the job will actually run, and reject bad requests
    # before writing anything to disk.
    source_job = None
    rerun = False
    if mode == "reanimate":
        if _present(source_video) == bool(source_job_id):
            raise HTTPException(status_code=400, detail="Reanimate needs exactly one of source_video or source_job_id")
        if source_job_id:
            source_job = _completed_source_job(source_job_id)
        if not _present(driving_video):
            if source_job is None:
                raise HTTPException(status_code=400, detail="Reanimating an uploaded video needs a driving_video")
            rerun = True
    elif not _present(reference_image):
        raise HTTPException(status_code=400, detail="reference_image is required")
    elif mode == "motion_transfer" and not _present(driving_video):
        raise HTTPException(status_code=400, detail="driving_video is required for motion transfer")

    job_mode = source_job["params"]["mode"] if rerun else mode
    if rerun and not prompt.strip():
        prompt = source_job["params"]["prompt"]
    if job_mode == "image_to_video" and not prompt.strip():
        raise HTTPException(status_code=400, detail="Animating an image needs a prompt describing the motion")

    backend = backend or settings.default_backend
    info = _require_usable_backend(backend, ENGINE_MODE[job_mode])
    _validate_clip(clip_len, fps, min(settings.max_clip_seconds, info["max_clip_seconds"] or settings.max_clip_seconds))
    _validate_output_fps(output_fps, fps)

    job_id = new_job_id()
    try:
        if rerun:
            ref_path = copy_input(Path(source_job["reference_image_path"]), job_id, "image")
            original_video = source_job["driving_video_path"]
            video_path = copy_input(Path(original_video), job_id, "video") if original_video else None
        elif mode == "reanimate":
            if source_job is not None:
                source_path = Path(source_job["output_video_path"])
            else:
                source_path = await save_upload(source_video, "source", job_id)
            ref_path = job_upload_dir(job_id) / "image.png"
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            extract_first_frame(source_path, ref_path)
            video_path = await save_upload(driving_video, "video", job_id)
        else:
            ref_path = await save_upload(reference_image, "image", job_id)
            video_path = await save_upload(driving_video, "video", job_id) if mode == "motion_transfer" else None
    except ValueError as exc:
        shutil.rmtree(job_upload_dir(job_id), ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        shutil.rmtree(job_upload_dir(job_id), ignore_errors=True)
        raise HTTPException(status_code=400, detail="The source job's input files are missing") from exc

    params = JobParams(
        mode=job_mode, source_job_id=source_job_id or None,
        width=width, height=height, fps=fps, output_fps=output_fps, clip_len=clip_len,
        sample_guide_scale=sample_guide_scale, steps=steps, seed=seed,
        prompt=prompt, prompt_ref=prompt_ref, backend=backend,
    )
    jobs_service.create_job(job_id, params, ref_path, video_path)
    job = jobs_service.get_job(job_id)
    return _to_job_out(job)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs() -> list[JobOut]:
    return [_to_job_out(j) for j in jobs_service.list_jobs()]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    job = jobs_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str) -> JobOut:
    job = jobs_service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_out(job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> Response:
    try:
        deleted = jobs_service.delete_job(job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return Response(status_code=204)


@router.get("/jobs/{job_id}/result")
def get_job_result(job_id: str) -> FileResponse:
    job = jobs_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not job["output_video_path"]:
        raise HTTPException(status_code=409, detail=f"Job is not completed (status={job['status']})")
    path = Path(job["output_video_path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Result file no longer exists")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")
