"""Subprocess helper shared by the engine adapters.

Every backend shells out (ffmpeg, a model's demo script, torchrun). Running
those through `run_cancellable` lets a job be cancelled mid-run: the child is
started in its own process group so a cancel tears down the whole tree
(torchrun spawns one worker per GPU), not just the top-level process.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path

_POLL_SECONDS = 0.5
_TERM_GRACE_SECONDS = 10


class JobCancelled(Exception):
    """Raised when a job's cancel event fires while its engine is running."""


def run_cancellable(
    cmd: list[str],
    *,
    cancel_event: threading.Event | None = None,
    cwd: str | Path | None = None,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run `cmd` to completion, capturing text output, unless `cancel_event` fires first."""
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    # communicate() in a helper thread drains the pipes so a chatty child can't
    # block on a full pipe buffer while we wait on the cancel event.
    output: dict[str, str] = {}

    def _drain() -> None:
        output["stdout"], output["stderr"] = proc.communicate()

    drainer = threading.Thread(target=_drain, daemon=True)
    drainer.start()

    while drainer.is_alive():
        drainer.join(_POLL_SECONDS)
        if cancel_event is not None and cancel_event.is_set() and proc.poll() is None:
            _terminate_group(proc)
            drainer.join()
            raise JobCancelled()

    return subprocess.CompletedProcess(cmd, proc.returncode, output.get("stdout", ""), output.get("stderr", ""))


def _terminate_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=_TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass
