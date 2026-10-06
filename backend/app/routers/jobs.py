from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .. import jobs as jobs_service
from ..config import settings
from ..inference.registry import available_backends, backend_info
from ..models import JobOut, JobParams
from ..storage import new_job_id, save_upload

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


def _validate_clip(clip_len: int, fps: int) -> None:
    if fps < 1:
        raise HTTPException(status_code=400, detail="fps must be at least 1")
    if clip_len < 1:
        raise HTTPException(status_code=400, detail="clip_len must be at least 1 frame")
    if clip_len / fps > settings.max_clip_seconds:
        raise HTTPException(
            status_code=400,
            detail=f"Clip is too long: {clip_len} frames at {fps}fps is {clip_len / fps:.1f}s; "
            f"the maximum is {settings.max_clip_seconds}s",
        )


def _require_usable_backend(name: str) -> None:
    known = {b["name"]: b for b in backend_info()}
    if name not in known:
        raise HTTPException(status_code=400, detail=f"Unknown animation backend '{name}'. Known: {sorted(known)}")
    if not known[name]["available"]:
        raise HTTPException(
            status_code=400,
            detail=f"Animation backend '{name}' is not set up on this server (see docs/MODEL_SETUP.md). "
            f"Available: {available_backends()}",
        )


@router.post("/jobs", response_model=JobOut)
async def create_job(
    reference_image: UploadFile = File(...),
    driving_video: UploadFile = File(...),
    backend: str | None = Form(None),
    prompt: str = Form(""),
    prompt_ref: str = Form("reference video of the character's motion"),
    width: int = Form(720),
    height: int = Form(1280),
    fps: int = Form(24),
    clip_len: int = Form(81),
    sample_guide_scale: float = Form(3.0),
    steps: int = Form(40),
    seed: int = Form(-1),
) -> JobOut:
    backend = backend or settings.default_backend
    # Reject before writing uploads to disk, rather than failing later in the worker.
    _require_usable_backend(backend)
    _validate_clip(clip_len, fps)

    job_id = new_job_id()
    try:
        ref_path = await save_upload(reference_image, "image", job_id)
        video_path = await save_upload(driving_video, "video", job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    params = JobParams(
        width=width, height=height, fps=fps, clip_len=clip_len,
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
