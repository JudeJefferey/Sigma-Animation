from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

from .db import get_conn, row_to_job_dict, transaction
from .inference.base import AnimationRequest
from .inference.registry import get_backend
from .models import JobParams
from .storage import job_output_dir

_work_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id: str, params: JobParams, reference_image_path: Path, driving_video_path: Path) -> None:
    with transaction() as conn:
        conn.execute(
            """INSERT INTO jobs
               (id, status, backend, params, reference_image_path, driving_video_path,
                output_video_path, error, processing_seconds, created_at, updated_at)
               VALUES (?, 'queued', ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
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


def _set_status(job_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with transaction() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", (*fields.values(), job_id))


def _process_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return

    _set_status(job_id, status="running")
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
        )
        result = backend.run(request)
        _set_status(
            job_id,
            status="completed",
            output_video_path=str(result.output_video_path),
            processing_seconds=result.processing_seconds,
        )
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
