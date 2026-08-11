from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobParams(BaseModel):
    width: int = 720
    height: int = 1280
    fps: int = 24
    clip_len: int = 81
    sample_guide_scale: float = 3.0
    steps: int = 40
    seed: int = -1
    prompt: str = ""
    prompt_ref: str = "reference video of the character's motion"
    backend: str = Field(default="mock", description="Which animation engine to use")


class JobOut(BaseModel):
    id: str
    status: JobStatus
    backend: str
    params: JobParams
    output_video_url: str | None = None
    error: str | None = None
    processing_seconds: float | None = None
    created_at: str
    updated_at: str
