"""Mock backend used for local development and tests on machines without a GPU.

It does not call any external AI service. It produces a short synthetic clip
by looping the reference image, so the full upload -> job -> download pipeline
can be exercised end-to-end without the ~14B-parameter Wan-Animate-2 weights
or multi-GPU hardware.
"""
from __future__ import annotations

import shutil
import subprocess
import time

from .base import AnimationBackend, AnimationRequest, AnimationResult


class MockAnimationBackend(AnimationBackend):
    name = "mock"

    def is_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def run(self, request: AnimationRequest) -> AnimationResult:
        start = time.time()
        request.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = request.output_dir / "result.mp4"

        duration = max(1, request.clip_len // request.fps)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(request.reference_image_path),
            "-t", str(duration),
            "-vf", f"scale={request.width}:{request.height},fps={request.fps}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"mock backend ffmpeg failed: {proc.stderr}")

        return AnimationResult(
            output_video_path=output_path,
            processing_seconds=time.time() - start,
            log="mock backend: looped reference image, no model inference performed",
        )
