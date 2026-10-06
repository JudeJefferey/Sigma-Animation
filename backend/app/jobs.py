from __future__ import annotations

import json
import queue
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .db import get_conn, row_to_job_dict, transaction
from .inference.base import AnimationRequest
from .inference.process import JobCancelled
from .inference.registry import get_backend
from .models import JobParams
from .storage import job_output_dir, job_upload_dir

_work_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()

# Cancel events for the job currently running, keyed by job id.
_running_cancel_events: dict[str, threading.Event] = {}
_running_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id: str, params: JobParams, reference_image_path: Path, driving_video_path: Path) -> None:
    with transaction() as conn:
        conn.execute(
            """INSERT INTO jobs
               (id, status, backend, params, reference_image_path, driving_video_path,
                output_video_path, error, log, processing_seconds, created_at, updated_at)
               VALUES (?, 'queued', ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)""",
            (
                job_id,
                params.backend,
                json.dumps(params.model_dump()),
                str(reference_image_path),
                str(driving_video_path),
                _now(),
                _now(),
            ),
        )
    _work_queue.put(job_id)


def get_job(job_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_job_dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [row_to_job_dict(r) for r in rows]


def _set_status(job_id: str, only_if_status: str | None = None, **fields) -> bool:
    """Update a job row; with `only_if_status`, only when it is still in that status.

    Returns whether a row was updated, so callers racing the worker (cancel vs.
    pickup) can tell who won.
    """
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    sql = f"UPDATE jobs SET {set_clause} WHERE id = ?"
    args = [*fields.values(), job_id]
    if only_if_status is not None:
        sql += " AND status = ?"
        args.append(only_if_status)
    with transaction() as conn:
        return conn.execute(sql, args).rowcount > 0


def cancel_job(job_id: str) -> dict | None:
    """Cancel a queued or running job. Returns the updated job, or None if it doesn't exist.

    A queued job is marked cancelled immediately. A running job has its cancel
    event set; the worker kills the engine subprocess and marks it cancelled.
    Jobs that already finished are returned unchanged.
    """
    job = get_job(job_id)
    if job is None:
        return None
    if job["status"] == "queued" and _set_status(job_id, only_if_status="queued", status="cancelled"):
        return get_job(job_id)
    with _running_lock:
        event = _running_cancel_events.get(job_id)
    if event is not None:
        event.set()
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    """Delete a finished or queued job and its files. Running jobs must be cancelled first."""
    job = get_job(job_id)
    if job is None:
        return False
    if job["status"] == "running":
        raise RuntimeError("Job is running; cancel it before deleting")
    with transaction() as conn:
        # Re-check inside the transaction so a job picked up meanwhile isn't deleted mid-run.
        deleted = conn.execute(
            "DELETE FROM jobs WHERE id = ? AND status != 'running'", (job_id,)
        ).rowcount
    if not deleted:
        raise RuntimeError("Job is running; cancel it before deleting")
    shutil.rmtree(job_upload_dir(job_id), ignore_errors=True)
    shutil.rmtree(job_output_dir(job_id), ignore_errors=True)
    return True


def _process_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return

    cancel_event = threading.Event()
    with _running_lock:
        _running_cancel_events[job_id] = cancel_event
    try:
        # Only pick up jobs still queued: it may have been cancelled or deleted while waiting.
        if not _set_status(job_id, only_if_status="queued", status="running"):
            return
        _run_backend(job_id, job, cancel_event)
    finally:
        with _running_lock:
            _running_cancel_events.pop(job_id, None)


def _run_backend(job_id: str, job: dict, cancel_event: threading.Event) -> None:
    try:
        params = JobParams(**job["params"])
        backend = get_backend(params.backend)
        request = AnimationRequest(
            reference_image_path=Path(job["reference_image_path"]),
            driving_video_path=Path(job["driving_video_path"]),
            output_dir=job_output_dir(job_id),
            width=params.width,
            height=params.height,
            fps=params.fps,
            clip_len=params.clip_len,
            sample_guide_scale=params.sample_guide_scale,
            steps=params.steps,
            seed=params.seed,
            prompt=params.prompt,
            prompt_ref=params.prompt_ref,
            cancel_event=cancel_event,
        )
        result = backend.run(request)
        _set_status(
            job_id,
            status="completed",
            output_video_path=str(result.output_video_path),
            processing_seconds=result.processing_seconds,
            log=result.log,
        )
    except JobCancelled:
        _set_status(job_id, status="cancelled", error="Cancelled by user")
    except Exception as exc:  # noqa: BLE001 - surface any backend failure on the job
        _set_status(job_id, status="failed", error=str(exc))


def _worker_loop() -> None:
    while True:
        job_id = _work_queue.get()
        try:
            _process_job(job_id)
        finally:
            _work_queue.task_done()


def start_worker() -> None:
    """Start the single background worker thread (idempotent).

    Animation inference is heavy (GPU-bound), so jobs are processed one at a
    time by design rather than in a thread pool.
    """
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, daemon=True, name="sigma-animation-worker")
        thread.start()
        _worker_started = True


def requeue_incomplete_jobs() -> None:
    """On startup, resume queued jobs and fail jobs that were mid-run when the process died."""
    conn = get_conn()
    stuck = conn.execute("SELECT id FROM jobs WHERE status = 'running'").fetchall()
    for row in stuck:
        _set_status(row["id"], status="failed", error="Interrupted by server restart")

    queued = conn.execute("SELECT id FROM jobs WHERE status = 'queued'").fetchall()
    for row in queued:
        _work_queue.put(row["id"])
