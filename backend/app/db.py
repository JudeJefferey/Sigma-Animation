from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    backend TEXT NOT NULL,
    params TEXT NOT NULL,
    reference_image_path TEXT NOT NULL,
    driving_video_path TEXT NOT NULL,
    output_video_path TEXT,
    error TEXT,
    processing_seconds REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
        with _lock:
            _conn.execute(SCHEMA)
            _conn.commit()
    return _conn


@contextmanager
def transaction():
    conn = get_conn()
    with _lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def row_to_job_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["params"] = json.loads(d["params"])
    return d
