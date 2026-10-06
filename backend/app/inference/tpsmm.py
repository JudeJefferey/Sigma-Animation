"""Backend adapter for Thin-Plate-Spline-Motion-Model (TPSMM).

TPSMM (https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model, MIT
licensed) is a small, pre-diffusion motion-transfer model: a source image is
warped frame-by-frame to match the motion in a driving video using learned
keypoints and a thin-plate-spline deformation, then inpainted. No denoising
loop, no multi-billion-parameter transformer -- the whole checkpoint is a
few hundred MB and its own `demo.py` supports a `--cpu` flag. That makes it
the backend that can realistically run on modest hardware (including plain
CPU boxes), unlike Wan-Animate-2 which needs a multi-GPU cluster.

Trade-off: quality and generality are well below Wan-Animate-2. TPSMM warps
an existing image rather than generating fresh appearance, so it only
tracks motion the source image can plausibly deform into, and each
checkpoint is trained for one domain (talking heads, full-body Tai Chi
motion, etc.) rather than open-ended prompted generation.

Configure via environment variables (see backend/app/config.py):
  TPSMM_REPO        path to a checked-out Thin-Plate-Spline-Motion-Model repo
  TPSMM_CONFIG      path to a model YAML (defaults to <repo>/config/vox-256.yaml)
  TPSMM_CHECKPOINT  path to a .pth.tar checkpoint (defaults to <repo>/checkpoints/vox.pth.tar)
  TPSMM_PYTHON      python executable with the repo's deps installed
  TPSMM_MODE        standard | relative | avd (default: relative)
  TPSMM_IMG_SHAPE   the resolution the checkpoint was trained at (default: 256,256)
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from ..config import settings
from .base import AnimationBackend, AnimationRequest, AnimationResult
from .process import run_cancellable


class TPSMMBackend(AnimationBackend):
    name = "tpsmm"
    description = "Thin-Plate-Spline-Motion-Model: warps the reference image to follow the driving motion. Runs on CPU."

    def __init__(self) -> None:
        self.repo_dir = Path(settings.tpsmm_repo) if settings.tpsmm_repo else None
        self.python_bin = settings.tpsmm_python
        self.mode = settings.tpsmm_mode
        self.img_shape = settings.tpsmm_img_shape

    @property
    def config_path(self) -> Path | None:
        if settings.tpsmm_config:
            return Path(settings.tpsmm_config)
        return self.repo_dir / "config" / "vox-256.yaml" if self.repo_dir else None

    @property
    def checkpoint_path(self) -> Path | None:
        if settings.tpsmm_checkpoint:
            return Path(settings.tpsmm_checkpoint)
        return self.repo_dir / "checkpoints" / "vox.pth.tar" if self.repo_dir else None

    def is_available(self) -> bool:
        if not self.repo_dir or not self.repo_dir.is_dir():
            return False
        if not (self.repo_dir / "demo.py").is_file():
            return False
        if not self.config_path or not self.config_path.is_file():
            return False
        if not self.checkpoint_path or not self.checkpoint_path.is_file():
            return False
        if shutil.which(self.python_bin) is None and not Path(self.python_bin).is_file():
            return False
        return True

    def run(self, request: AnimationRequest) -> AnimationResult:
        if not self.is_available():
            raise RuntimeError(
                "TPSMM backend is not configured. Set TPSMM_REPO to a checked-out copy of "
                "https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model with a checkpoint "
                "downloaded, per docs/MODEL_SETUP.md."
            )

        start = time.time()
        request.output_dir.mkdir(parents=True, exist_ok=True)

        trimmed_driving = request.output_dir / "driving_trimmed.mp4"
        duration = max(1, request.clip_len // max(request.fps, 1))
        self._trim_video(request.driving_video_path, trimmed_driving, duration, request.fps, request.cancel_event)

        raw_result = request.output_dir / "raw_result.mp4"
        cmd = [
            self.python_bin, "demo.py",
            "--config", str(self.config_path),
            "--checkpoint", str(self.checkpoint_path),
            "--source_image", str(request.reference_image_path.resolve()),
            "--driving_video", str(trimmed_driving.resolve()),
            "--result_video", str(raw_result.resolve()),
            "--img_shape", self.img_shape,
            "--mode", self.mode,
            "--cpu",
        ]
        proc = run_cancellable(cmd, cwd=self.repo_dir, cancel_event=request.cancel_event)
        if proc.returncode != 0 or not raw_result.is_file():
            raise RuntimeError(f"TPSMM inference failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}")

        final_result = request.output_dir / "result.mp4"
        self._rescale(raw_result, final_result, request.width, request.height, request.cancel_event)

        return AnimationResult(
            output_video_path=final_result,
            processing_seconds=time.time() - start,
            log=proc.stdout[-4000:],
        )

    @staticmethod
    def _trim_video(
        src: Path, dest: Path, duration_seconds: int, fps: int, cancel_event: threading.Event | None = None
    ) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(src.resolve()),
            "-t", str(duration_seconds),
            "-r", str(fps),
            "-an",
            str(dest.resolve()),
        ]
        proc = run_cancellable(cmd, cancel_event=cancel_event)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to trim driving video: {proc.stderr}")

    @staticmethod
    def _rescale(
        src: Path, dest: Path, width: int, height: int, cancel_event: threading.Event | None = None
    ) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(src.resolve()),
            "-vf", f"scale={width}:{height}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(dest.resolve()),
        ]
        proc = run_cancellable(cmd, cancel_event=cancel_event)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to rescale TPSMM output: {proc.stderr}")
