"""Engine-independent post-processing applied to a finished animation."""
from __future__ import annotations

import threading
from pathlib import Path

from .inference.process import run_cancellable

# Motion-compensated interpolation: synthesizes in-between frames from
# estimated motion rather than duplicating or blending frames.
_MINTERPOLATE = "minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"


def interpolate_fps(src: Path, dest: Path, fps: int, cancel_event: threading.Event | None = None) -> None:
    """Re-time `src` to `fps` by interpolating frames, keeping its duration."""
    duration = _duration_seconds(src, cancel_event)
    # minterpolate stops at the last source frame's timestamp, dropping that
    # frame's display time; pad with a cloned tail, then trim back to length.
    vf = "tpad=stop_mode=clone:stop_duration=1," + _MINTERPOLATE.format(fps=fps)
    cmd = [
        "ffmpeg", "-y", "-i", str(src.resolve()),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(dest.resolve()),
    ]
    proc = run_cancellable(cmd, cancel_event=cancel_event)
    if proc.returncode != 0:
        raise RuntimeError(f"Frame interpolation to {fps}fps failed: {proc.stderr[-4000:]}")


def _duration_seconds(path: Path, cancel_event: threading.Event | None) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path.resolve()),
    ]
    proc = run_cancellable(cmd, cancel_event=cancel_event)
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not read duration of {path.name}: {proc.stderr}") from exc
