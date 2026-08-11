# Setting up the Wan-Animate-2 engine

The app ships with a `mock` backend (no GPU needed) so you can develop and
test the full pipeline immediately. To generate real animations you need to
plug in a real engine. This doc covers [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2),
the reference implementation `app/inference/wan_animate2.py` wraps.

## Hardware

Per the upstream README, the default configs are tuned for **8x A800 GPUs**
at 720p, with 480p tested on 2x A800. This is a large model (14B params) --
plan accordingly. `WAN_ANIMATE2_NUM_GPUS` and the `sp_size`/`sharding_size`
fields in the YAML config must match your actual GPU count.

## Bare-metal / venv setup

```bash
git clone --recursive https://github.com/Wan-Video/Wan-Animate-2.git
cd Wan-Animate-2
conda create -n wan_animate_2 python==3.11 -y && conda activate wan_animate_2
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
pip install flash-attn --no-build-isolation
pip install -e .

pip install "huggingface_hub[cli]"
huggingface-cli download Wan-AI/Wan2.2-Animate-2-14B --local-dir ./ckpts/
```

Then point Sigma-Animation's backend at it:

```bash
export WAN_ANIMATE2_REPO=/path/to/Wan-Animate-2
export WAN_ANIMATE2_CONFIG=/path/to/Wan-Animate-2/infer/wan_animate_2.yaml
export WAN_ANIMATE2_PYTHON=/path/to/conda/envs/wan_animate_2/bin/python
export WAN_ANIMATE2_NUM_GPUS=8
export SIGMA_DEFAULT_BACKEND=wan-animate-2
```

Restart the backend (`uvicorn app.main:app`). `GET /api/backends` should now
list `wan-animate-2` once the repo, demo script, and python executable are
all found on disk (see `WanAnimate2Backend.is_available`).

## Docker / GPU compose

`backend/Dockerfile.gpu` builds a CUDA image with Wan-Animate-2 cloned and
installed. Weights are not baked into the image -- download them to a local
`./ckpts` directory and mount it:

```bash
mkdir -p ckpts
huggingface-cli download Wan-AI/Wan2.2-Animate-2-14B --local-dir ./ckpts/

docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

This requires the host to have `nvidia-container-toolkit` installed.

## Swapping in a different model later

`app/inference/base.py` defines the `AnimationBackend` interface
(`is_available()` / `run(request) -> AnimationResult`). To add another
self-hosted engine, implement that interface in a new file under
`app/inference/`, register it in `app/inference/registry.py`, and it becomes
selectable from the UI's engine dropdown -- no changes needed elsewhere.
