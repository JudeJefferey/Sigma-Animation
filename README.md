# Sigma Animation

A self-hosted character animation app: upload a reference image and a
driving video, get back a video of the reference character performing the
driving motion. Runs entirely on infrastructure you control -- it does not
call any hosted third-party AI API.

The included reference engine is [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2),
but the inference layer is pluggable (see `docs/ARCHITECTURE.md`) so other
open-source animation models can be swapped in.

## Quick start (no GPU required)

Runs the API and UI against the built-in `mock` backend, useful for trying
the app or developing on it without any model weights.

```bash
docker compose up --build
```

Open http://localhost:8080.

## Running with the real Wan-Animate-2 engine

See [`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md) -- requires a multi-GPU
Linux host and downloading the model weights.

## Local development (without Docker)

Backend:

```bash
cd backend
pip install -r requirements-dev.txt   # includes test-only deps (Pillow)
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000` by default.

### Tests

```bash
cd backend
pytest
```

## Project layout

```
backend/    FastAPI app, job queue, pluggable inference backends
frontend/   React + TypeScript UI
docs/       architecture and model setup docs
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit
together.
