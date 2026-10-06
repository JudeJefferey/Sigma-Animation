"""Backend adapter for the self-hosted Wan-Animate-2 model.

Wan-Animate-2 is a large multi-GPU diffusion transformer (14B params) that
needs its own environment (torch/flash-attn/distributed launch) and is not
safe or practical to import in-process inside a web API. This adapter shells
out to the model's own CLI entrypoint (`infer/wan_animate_2_demo.py`) via
`torchrun`, on whatever GPU hardware the operator has provisioned. Nothing
here talks to any hosted/third-party AI API -- the weights and compute are
entirely local to the deployment.

Configure via environment variables (see backend/app/config.py):
  WAN_ANIMATE2_REPO       path to a checked-out Wan-Animate-2 repo
  WAN_ANIMATE2_CONFIG     path to the model YAML config (relative to repo/infer
                           or absolute)
  WAN_ANIMATE2_PYTHON     python executable inside the model's env
  WAN_ANIMATE2_NUM_GPUS   number of GPUs to launch with torchrun
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..config import settings
from .base import AnimationBackend, AnimationRequest, AnimationResult
from .process import run_cancellable


class WanAnimate2Backend(AnimationBackend):
    name = "wan-animate-2"
    description = "Wan-Animate-2: full generative character animation. Needs a multi-GPU host."

    def __init__(self) -> None:
        self.repo_dir = Path(settings.wan_animate2_repo) if settings.wan_animate2_repo else None
        self.config_path = settings.wan_animate2_config
        self.python_bin = settings.wan_animate2_python
        self.num_gpus = settings.wan_animate2_num_gpus

    def is_available(self) -> bool:
        if not self.repo_dir or not self.repo_dir.is_dir():
            return False
        demo_script = self.repo_dir / "infer" / "wan_animate_2_demo.py"
        if not demo_script.is_file():
            return False
        if shutil.which(self.python_bin) is None and not Path(self.python_bin).is_file():
            return False
        return True

    def run(self, request: AnimationRequest) -> AnimationResult:
        if not self.is_available():
            raise RuntimeError(
                "Wan-Animate-2 backend is not configured. Set WAN_ANIMATE2_REPO to a "
                "checked-out copy of https://github.com/Wan-Video/Wan-Animate-2 with "
                "model weights downloaded, per docs/MODEL_SETUP.md."
            )

        start = time.time()
        request.output_dir.mkdir(parents=True, exist_ok=True)
        infer_dir = self.repo_dir / "infer"

        cmd = [
            "torchrun", "--nproc_per_node", str(self.num_gpus),
            str(infer_dir / "wan_animate_2_demo.py"),
            "--prompt", request.prompt,
            "--refer-img-file", str(request.reference_image_path.resolve()),
            "--refer-video-file", str(request.driving_video_path.resolve()),
            "--config", self.config_path,
            "--width", str(request.width),
            "--height", str(request.height),
            "--fps", str(request.fps),
            "--clip_len", str(request.clip_len),
            "--sample_guide_scale", str(request.sample_guide_scale),
            "--step", str(request.steps),
            "--seed", str(request.seed),
            "--prompt_ref", request.prompt_ref,
            "--output-dir", str(request.output_dir.resolve()),
        ]

        proc = run_cancellable(
            cmd,
            cwd=infer_dir,
            env=self._build_env(),
            cancel_event=request.cancel_event,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Wan-Animate-2 inference failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}"
            )

        result_video = self._find_result_video(request.output_dir)
        if result_video is None:
            raise RuntimeError(
                "Wan-Animate-2 process exited successfully but no results.mp4 was found "
                f"under {request.output_dir}"
            )

        return AnimationResult(
            output_video_path=result_video,
            processing_seconds=time.time() - start,
            log=proc.stdout[-4000:],
        )

    def _build_env(self) -> dict:
        import os

        env = os.environ.copy()
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{self.repo_dir}:{existing_path}" if existing_path else str(self.repo_dir)
        return env

    @staticmethod
    def _find_result_video(output_dir: Path) -> Path | None:
        # The upstream pipeline writes <output_dir>/session_<ts>/results.mp4
        candidates = sorted(output_dir.glob("session_*/results.mp4"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
        direct = output_dir / "results.mp4"
        return direct if direct.is_file() else None
