"""Backend adapter for Wan2.2 TI2V-5B: animate an image from a text prompt.

Wan2.2 (https://github.com/Wan-Video/Wan2.2, Apache 2.0) ships a 5B-parameter
text+image-to-video model that, per its README, runs on a single 24GB
consumer GPU (e.g. RTX 4090) and makes a 5-second 720p clip in under ~9
minutes. Unlike the motion-transfer engines it needs no driving video: the
motion comes from the prompt. Like the other engines, it runs as a
subprocess via the model repo's own `generate.py`.

Configure via environment variables (see backend/app/config.py):
  WAN_TI2V_REPO      path to a checked-out Wan2.2 repo
  WAN_TI2V_CKPT_DIR  path to the downloaded Wan2.2-TI2V-5B weights
                     (defaults to <repo>/Wan2.2-TI2V-5B)
  WAN_TI2V_PYTHON    python executable with the repo's deps installed
  WAN_TI2V_OFFLOAD   true (default) trades speed for memory so it fits in 24GB
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..config import settings
from .base import IMAGE_TO_VIDEO, AnimationBackend, AnimationRequest, AnimationResult
from .process import run_cancellable
from .video import rescale

# From Wan2.2's wan/configs/wan_ti2v_5B.py: the model generates at 24fps and
# its default (trained) clip is 121 frames, i.e. ~5 seconds.
_NATIVE_FPS = 24
_MAX_SECONDS = 5


class WanTI2VBackend(AnimationBackend):
    name = "wan-ti2v"
    description = "Wan2.2 TI2V-5B: animates the image from your prompt, no driving video. Needs a 24GB GPU."
    modes = frozenset({IMAGE_TO_VIDEO})
    max_clip_seconds = _MAX_SECONDS

    def __init__(self) -> None:
        self.repo_dir = Path(settings.wan_ti2v_repo) if settings.wan_ti2v_repo else None
        self.python_bin = settings.wan_ti2v_python
        self.offload = settings.wan_ti2v_offload

    @property
    def ckpt_dir(self) -> Path | None:
        if settings.wan_ti2v_ckpt_dir:
            return Path(settings.wan_ti2v_ckpt_dir)
        return self.repo_dir / "Wan2.2-TI2V-5B" if self.repo_dir else None

    def is_available(self) -> bool:
        if not self.repo_dir or not (self.repo_dir / "generate.py").is_file():
            return False
        if not self.ckpt_dir or not self.ckpt_dir.is_dir():
            return False
        return shutil.which(self.python_bin) is not None or Path(self.python_bin).is_file()

    def run(self, request: AnimationRequest) -> AnimationResult:
        if not self.is_available():
            raise RuntimeError(
                "Wan2.2 TI2V backend is not configured. Set WAN_TI2V_REPO to a checked-out copy of "
                "https://github.com/Wan-Video/Wan2.2 with the TI2V-5B weights downloaded, per "
                "docs/MODEL_SETUP.md."
            )
        if not request.prompt.strip():
            raise RuntimeError("Wan2.2 TI2V needs a prompt describing the motion")

        start = time.time()
        request.output_dir.mkdir(parents=True, exist_ok=True)
        raw_result = request.output_dir / "raw_result.mp4"

        cmd = [
            self.python_bin, "generate.py",
            "--task", "ti2v-5B",
            # The model only supports these two 720p sizes; the result is
            # rescaled to the requested size afterwards.
            "--size", "1280*704" if request.width >= request.height else "704*1280",
            "--ckpt_dir", str(self.ckpt_dir.resolve()),
            "--image", str(request.reference_image_path.resolve()),
            "--prompt", request.prompt,
            "--frame_num", str(self.frame_num(request.clip_len, request.fps)),
            "--sample_steps", str(request.steps),
            "--base_seed", str(request.seed),
            "--save_file", str(raw_result.resolve()),
        ]
        if self.offload:
            cmd += ["--offload_model", "True", "--convert_model_dtype", "--t5_cpu"]

        proc = run_cancellable(cmd, cwd=self.repo_dir, cancel_event=request.cancel_event)
        if proc.returncode != 0 or not raw_result.is_file():
            raise RuntimeError(f"Wan2.2 TI2V inference failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}")

        final_result = request.output_dir / "result.mp4"
        rescale(raw_result, final_result, request.width, request.height, request.fps, request.cancel_event)

        return AnimationResult(
            output_video_path=final_result,
            processing_seconds=time.time() - start,
            log=(proc.stdout + proc.stderr)[-4000:],
        )

    @staticmethod
    def frame_num(clip_len: int, fps: int) -> int:
        """Frames to generate at the model's 24fps for the requested duration.

        generate.py requires 4n+1 frames.
        """
        seconds = min(clip_len / max(fps, 1), _MAX_SECONDS)
        n = max(1, round((seconds * _NATIVE_FPS - 1) / 4))
        return 4 * n + 1
