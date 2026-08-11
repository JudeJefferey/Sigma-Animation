from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from .config import settings

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi", ".mkv"}


def _ensure_dirs() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)


def _validate_ext(filename: str, allowed: set[str], kind: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise ValueError(f"Unsupported {kind} file type '{ext}'. Allowed: {sorted(allowed)}")
    return ext


async def save_upload(file: UploadFile, kind: str, job_id: str) -> Path:
    """Persist an uploaded reference image or driving video for a job."""
    _ensure_dirs()
    allowed = ALLOWED_IMAGE_EXT if kind == "image" else ALLOWED_VIDEO_EXT
    ext = _validate_ext(file.filename or "", allowed, kind)

    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"{kind}{ext}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"File exceeds max upload size of {settings.max_upload_mb}MB")
            out.write(chunk)

    return dest


def job_output_dir(job_id: str) -> Path:
    return settings.outputs_dir / job_id


def new_job_id() -> str:
    return uuid.uuid4().hex
