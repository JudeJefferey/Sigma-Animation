from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import get_conn
from .jobs import requeue_incomplete_jobs, start_worker
from .routers.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    get_conn()
    start_worker()
    requeue_incomplete_jobs()
    yield


app = FastAPI(
    title="Sigma Animation API",
    description="Self-hosted character animation service. No third-party AI API involved.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
