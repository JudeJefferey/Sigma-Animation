"""Backend-agnostic interface for character animation inference engines.

Sigma-Animation never calls a hosted third-party AI API. Every inference
engine plugged in here runs on infrastructure the operator controls (local
GPU box, self-managed cloud instance, etc). Swapping engines means adding a
class here and registering it in `registry.py` -- nothing else in the app
changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnimationRequest:
    reference_image_path: Path
    driving_video_path: Path
    output_dir: Path
    width: int = 720
    height: int = 1280
    fps: int = 24
    clip_len: int = 81
    sample_guide_scale: float = 3.0
    steps: int = 40
    seed: int = -1
    prompt: str = ""
    prompt_ref: str = "reference video of the character's motion"
    # Set by the job queue when the user cancels; backends pass it to
    # `process.run_cancellable` so the engine subprocess is torn down.
    cancel_event: threading.Event = field(default_factory=threading.Event)


@dataclass
class AnimationResult:
    output_video_path: Path
    processing_seconds: float
    log: str = ""


class AnimationBackend(ABC):
    """A single animation engine (e.g. Wan-Animate-2, a mock, a future model)."""

    name: str
    description: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this backend's runtime deps/weights are present."""

    @abstractmethod
    def run(self, request: AnimationRequest) -> AnimationResult:
        """Run inference synchronously and return the produced video path."""
