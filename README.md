# Sigma Animation

A self-hosted character animation app: upload a reference image and a
driving video, get back a video of the reference character performing the
driving motion. Runs entirely on infrastructure you control -- it does not
call any hosted third-party AI API.

The inference layer is pluggable (see `docs/ARCHITECTURE.md`), so different
self-hosted models can be swapped in. Three are wired up out of the box:

| Backend | Needs | What it does |
| --- | --- | --- |
| `mock` | ffmpeg only | Loops the reference image -- no model, just exercises the pipeline |
| `tpsmm` | CPU, ~350MB checkpoint | Real motion transfer via [Thin-Plate-Spline-Motion-Model](https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model) (MIT) -- warps the source image to follow the driving motion |
| `wan-animate-2` | 8x A800/A100-class GPUs | Full generative character animation via [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2) |

## Quick start (no GPU required)

Runs the API and UI against the built-in `mock` backend, useful for trying
the app or developing on it without any model weights.

```bash
docker compose up --build
```

Open http://localhost:8080.

## Running with a real engine

See [`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md):
- `tpsmm` runs on CPU/modest hardware -- good default for actually seeing
  real generated output.
- `wan-animate-2` needs a multi-GPU Linux host but produces much higher
  quality, open-ended results.

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
