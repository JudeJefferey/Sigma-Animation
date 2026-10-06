"""Small ffmpeg helpers shared by the engine adapters and job intake."""
from __future__ import annotations

import threading
from pathlib import Path

from .process import run_cancellable


def rescale(
    src: Path,
    dest: Path,
    width: int,
    height: int,
    fps: int | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Re-encode `src` at `width`x`height` (and `fps`, if given) as browser-playable H.264."""
    vf = f"scale={width}:{height}" + (f",fps={fps}" if fps else "")
    cmd = [
        "ffmpeg", "-y", "-i", str(src.resolve()),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(dest.resolve()),
    ]
    proc = run_cancellable(cmd, cancel_event=cancel_event)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to rescale video: {proc.stderr[-4000:]}")


def extract_first_frame(src: Path, dest: Path) -> None:
    """Save the first frame of video `src` as image `dest`."""
    cmd = ["ffmpeg", "-y", "-i", str(src.resolve()), "-frames:v", "1", str(dest.resolve())]
    proc = run_cancellable(cmd)
    if proc.returncode != 0 or not dest.is_file():
        raise ValueError("Could not read a frame from the source video; is it a valid video file?")
