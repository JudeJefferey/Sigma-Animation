# Architecture

Sigma-Animation is a self-hosted web app for character animation: upload a
reference image and a driving video, get back a video of the reference
character performing the driving motion. It does not call any third-party AI
API -- inference runs on infrastructure the operator controls.

```
frontend (React/Vite)  --HTTP-->  backend (FastAPI)  --subprocess-->  animation engine
                                        |
                                        v
                                  SQLite job store
                                  local file storage (uploads/outputs)
```

## Backend

- **`app/main.py`** -- FastAPI app, starts a background worker thread and
  requeues any interrupted jobs on boot.
- **`app/routers/jobs.py`** -- HTTP surface: submit a job (multipart upload of
  image + video + params), poll job status, download the result.
- **`app/jobs.py`** -- job persistence (SQLite) and a single-worker queue.
  Animation inference is GPU-bound and heavyweight, so jobs run one at a time
  by design rather than in a thread/process pool.
- **`app/inference/`** -- the pluggable engine layer:
  - `base.py` defines `AnimationBackend`, `AnimationRequest`, `AnimationResult`.
  - `mock.py` is a dependency-light backend (ffmpeg only) for local dev and
    CI -- it does not run any model, it just loops the reference image so the
    full pipeline (upload -> queue -> job -> download) is exercisable without
    a GPU.
  - `tpsmm.py` shells out to a self-hosted Thin-Plate-Spline-Motion-Model
    checkout. It's a small (few hundred MB) keypoint-and-warp model with its
    own `--cpu` inference mode, so this is the backend that can realistically
    run without a GPU -- lower quality and generality than Wan-Animate-2
    (it warps the source image rather than generating fresh appearance, and
    each checkpoint is domain-specific), but real model output on modest
    hardware.
  - `wan_animate2.py` shells out to a self-hosted Wan-Animate-2 checkout via
    `torchrun`. This keeps the heavy multi-GPU model process isolated from the
    lightweight API process.
  - `registry.py` maps a `backend` name to an implementation. Adding a new
    engine (a different open-source animation model) means adding one file
    here plus a registry entry -- nothing else in the app changes.

## Frontend

Vite + React + TypeScript, single page: an upload form and a list of jobs
that poll for status and render the finished video inline. No build-time
dependency on any AI vendor SDK.

## Data flow

1. Client `POST /api/jobs` with `reference_image`, `driving_video`, and
   generation params (resolution, fps, steps, prompt, which `backend`).
2. Backend validates file types/sizes, saves them under
   `data/uploads/<job_id>/`, inserts a `queued` row, and enqueues the job id.
3. The worker thread picks up the job, marks it `running`, and calls the
   selected `AnimationBackend.run(...)`.
4. On success the row is marked `completed` with the output video path; the
   client can then `GET /api/jobs/{id}/result` to stream the file.
5. On failure the row is marked `failed` with the error message.

## Why a subprocess boundary for the real model

Wan-Animate-2 is a 14B-parameter diffusion transformer that expects a
dedicated conda/CUDA environment, `flash-attn`, and a multi-GPU distributed
launch (`torchrun`, FSDP sharding). Importing that in-process inside a web API
would couple the API's lifecycle to a very heavy, GPU-pinned process and make
crashes/OOMs take down the whole service. Running it as a subprocess per job
keeps the API lightweight and lets the model process be restarted, scheduled,
or moved to different hardware independently.
