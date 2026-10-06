# Sigma Animation

A self-hosted character animation app with three modes:

- **Copy motion**: a character image performs the motion from a driving video.
- **Animate image**: an image comes to life from a text prompt, no video needed.
- **Reanimate video**: give an uploaded video, or a previous result, new
  motion; or re-run a previous result with new settings.

Runs entirely on infrastructure you control -- it does not call any hosted
third-party AI API.

The inference layer is pluggable (see `docs/ARCHITECTURE.md`), so different
self-hosted models can be swapped in. Four are wired up out of the box:

| Backend | Modes | Needs | What it does |
| --- | --- | --- | --- |
| `mock` | all | ffmpeg only | Loops the reference image -- no model, just exercises the pipeline |
| `tpsmm` | copy motion, reanimate | CPU, ~350MB checkpoint | Real motion transfer via [Thin-Plate-Spline-Motion-Model](https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model) (MIT) -- warps the source image to follow the driving motion |
| `wan-animate-2` | copy motion, reanimate | 8x A800/A100-class GPUs | Full generative character animation via [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2) |
| `wan-ti2v` | animate image | One 24GB GPU (e.g. RTX 4090) | Animates an image from a text prompt via [Wan2.2 TI2V-5B](https://github.com/Wan-Video/Wan2.2) (Apache 2.0), up to 5 seconds |

## How to run it

There are two parts: a Python **backend** (the API and job runner) and a web
**frontend**. You run both on your own machine and use the app in a browser.
Out of the box it uses the `mock` engine, which just loops your image so you
can try the app with no model download. To get real animation, see
[Step 4](#step-4-optional-get-real-animation-with-tpsmm).

### Step 1: Get the code

```bash
git clone https://github.com/JudeJefferey/Sigma-Animation.git
cd Sigma-Animation
```

### Step 2: Start the app

Pick **one** of the two options below.

#### Option A: Docker (easiest)

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or
Docker Engine with Compose).

```bash
docker compose up --build
```

Open **http://localhost:8080**. Stop it with `Ctrl+C`.

#### Option B: Without Docker

Needs **Python 3.11+**, **Node.js 18+**, and **ffmpeg** on your `PATH`
(`brew install ffmpeg`, `sudo apt install ffmpeg`, or `winget install ffmpeg`).
Use two terminals.

Terminal 1 (backend, serves the API on port 8000):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Terminal 2 (frontend, serves the web UI on port 5173):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server forwards `/api` requests to the
backend on port 8000.

### Step 3: Make an animation

Pick a mode with the tabs at the top of the form:

- **Copy motion**: upload a **reference image** (the character, PNG/JPG/WebP)
  and a **driving video** (the motion to copy, MP4/WebM/MOV).
- **Animate image**: upload an image and write a **motion prompt** describing
  what should happen, e.g. "the woman turns her head and smiles, hair blowing
  in the wind". Needs the `wan-ti2v` engine for real output (see Step 4).
- **Reanimate video**: choose the video to reanimate, either **Upload a
  video** or **A previous result**, then:
  - add a **new driving video**: the character is taken from the source
    video's first frame and performs the new motion; or
  - (previous results only) leave the driving video empty: the earlier job is
    **re-run from its original inputs** with whatever settings you pick now
    (length, FPS, smoothing, resolution, engine). Its prompt is reused unless
    you type a new one.

Then set the rest of the form:

- **Engine**: engines that aren't set up, or can't do the chosen mode, are
  greyed out.
- **Clip length**: how many seconds of animation to make, from 1 to 60 (some
  engines allow less, e.g. `wan-ti2v` is limited to 5). If the driving video is
  shorter, TPSMM's output stops where the video ends.
- **Output FPS** (optional): pick 30-120 for smoother motion. The engine
  still generates at the **FPS** you set, then ffmpeg fills in the frames in
  between. This is much cheaper than generating at a high FPS: each generated
  frame costs a full model step, while interpolation takes seconds. Fast or
  complex motion can show some warping in the filled-in frames; for the best
  quality, generate at 24-30 FPS and smooth to 60.

Click **Generate animation** (or **Re-run with these settings**). The job
appears in the list on the right. From there you can watch it, download it,
open the engine log, cancel it while it runs, or delete it when it's done.

### Step 4 (optional): Get real animation with TPSMM

TPSMM runs on an ordinary CPU, no GPU needed. Use **Option B** above for this,
because the Docker setup doesn't pass these settings into the container.

1. Get the model code and install its dependencies:
   ```bash
   git clone https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model.git
   cd Thin-Plate-Spline-Motion-Model
   pip install torch torchvision numpy scipy scikit-image imageio imageio-ffmpeg pyyaml tqdm matplotlib pandas
   ```
2. Download a trained checkpoint into its `checkpoints/` folder: `vox.pth.tar`
   for faces and portraits, or `taichi.pth.tar` for full-body motion. Links are
   in the model's README and in
   [`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md).
3. In the backend terminal, set these and restart the backend:
   ```bash
   export TPSMM_REPO=/path/to/Thin-Plate-Spline-Motion-Model
   export TPSMM_CONFIG=$TPSMM_REPO/config/vox-256.yaml        # taichi-256.yaml for taichi
   export TPSMM_CHECKPOINT=$TPSMM_REPO/checkpoints/vox.pth.tar
   export TPSMM_PYTHON=python3          # a Python that has the step-1 packages installed
   export SIGMA_DEFAULT_BACKEND=tpsmm
   uvicorn app.main:app --reload
   ```
   On Windows PowerShell, use `$env:TPSMM_REPO="C:\path\to\..."` instead of `export`.
4. Reload the web page. `tpsmm` is now selectable in the Engine dropdown.

TPSMM works at 256x256 and each checkpoint suits one kind of footage. A vox
checkpoint expects a face photo and a talking-head video, for example.

### Step 5 (optional): Animate images from a prompt with Wan2.2 TI2V

The **Animate image** mode needs a text-driven model. `wan-ti2v` uses Wan2.2's
TI2V-5B, which needs an NVIDIA GPU with at least 24GB of memory (e.g. RTX 4090)
and takes several minutes per clip (Wan's README: under ~9 minutes for 5
seconds of 720p on one consumer GPU). Setup:

```bash
git clone https://github.com/Wan-Video/Wan2.2.git
cd Wan2.2
pip install -r requirements.txt          # needs torch >= 2.4 with CUDA
pip install "huggingface_hub[cli]"
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir ./Wan2.2-TI2V-5B
```

Then, in the backend terminal:

```bash
export WAN_TI2V_REPO=/path/to/Wan2.2
export WAN_TI2V_PYTHON=python3          # a Python with Wan2.2's requirements installed
uvicorn app.main:app --reload
```

Details and options are in [`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md).

**Wan-Animate-2** gives much higher-quality results but needs a Linux server
with several data-center GPUs (8x A800/A100-class for 720p). Its setup is in
[`docs/MODEL_SETUP.md`](docs/MODEL_SETUP.md), with a GPU Docker stack in
`docker-compose.gpu.yml`.

### Settings

All settings are environment variables read by the backend (`backend/app/config.py`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIGMA_DEFAULT_BACKEND` | `mock` | Engine used when a job doesn't pick one |
| `SIGMA_DATA_DIR` | `./data` | Where uploads and results are stored |
| `SIGMA_DB_PATH` | `./data/sigma_animation.db` | SQLite job database |
| `SIGMA_MAX_UPLOAD_MB` | `200` | Maximum size per uploaded file |
| `SIGMA_MAX_OUTPUT_FPS` | `120` | Highest output (smoothed) FPS the API accepts |
| `SIGMA_MAX_CLIP_SECONDS` | `60` | Longest clip the API accepts (the web form also caps at 60) |
| `TPSMM_*` | | TPSMM engine setup (see Step 4) |
| `WAN_TI2V_*` | | Wan2.2 TI2V engine setup (see Step 5) |
| `WAN_ANIMATE2_*` | | Wan-Animate-2 engine setup (see `docs/MODEL_SETUP.md`) |

### Troubleshooting

- **The engine I want is greyed out.** The backend couldn't find that engine's
  files. For TPSMM, check that `TPSMM_REPO`, `TPSMM_CONFIG` and
  `TPSMM_CHECKPOINT` point to files that exist, then restart the backend.
  `http://localhost:8000/api/backends` shows what the backend detected.
- **Jobs fail immediately with an ffmpeg error.** ffmpeg isn't installed or
  isn't on your `PATH`. Run `ffmpeg -version` to check.
- **The page loads but shows no engines and jobs don't submit.** The backend
  isn't running, or isn't on port 8000. Check terminal 1.
- **Port already in use.** Another program is using 8000, 5173 or 8080. Stop
  it, or start the backend with `--port <other>` and run the frontend with
  `SIGMA_API_PROXY_TARGET=http://localhost:<other> npm run dev`.

### Running the tests

```bash
cd backend
pytest
```

### Responsible use

The app has no login and no content filtering: anyone who can reach it can
submit, view and delete jobs, so don't expose it to the internet as-is. Only
animate images you have the rights to use. Animating a real person without
their consent can be illegal regardless of the model's licence. TPSMM's
pretrained checkpoints come from research datasets (e.g. VoxCeleb) whose terms
restrict commercial use; Wan-Animate-2 is Apache 2.0.

## Project layout

```
backend/    FastAPI app, job queue, pluggable inference backends
frontend/   React + TypeScript UI
docs/       architecture and model setup docs
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit
together.
