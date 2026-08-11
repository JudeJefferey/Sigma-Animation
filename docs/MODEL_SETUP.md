# Setting up a real animation engine

The app ships with a `mock` backend (no GPU needed) so you can develop and
test the full pipeline immediately. Two real engines are wired up, at
opposite ends of the hardware spectrum:

| Backend | Model | Hardware | Quality |
| --- | --- | --- | --- |
| `tpsmm` | [Thin-Plate-Spline-Motion-Model](https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model) (MIT) | Runs on CPU, ~350MB checkpoint | Warps the source image to follow motion; domain-specific per checkpoint (faces, Tai Chi, etc), not open-ended generation |
| `wan-animate-2` | [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2) | 8x A800/A100-class GPUs for 720p | State of the art, full generative character animation |

## TPSMM (CPU-feasible)

TPSMM (CVPR 2022) is a pre-diffusion motion-transfer model: keypoints are
detected on the source image and driving video, and the source is warped
frame-by-frame with a thin-plate-spline deformation plus inpainting. No
denoising loop, no billion-parameter transformer -- it's small conv nets,
and its own `demo.py` has a `--cpu` flag.

### Setup

```bash
git clone https://github.com/yoyo-nb/Thin-Plate-Spline-Motion-Model.git
cd Thin-Plate-Spline-Motion-Model
pip install torch torchvision numpy scipy scikit-image imageio imageio-ffmpeg pyyaml tqdm matplotlib pandas
```

Download a checkpoint (hosted on Google Drive / Yandex / Baidu Yun by the
authors -- see the repo's README for current links; there's also a
community mirror on [Hugging Face](https://huggingface.co/spaces/AlekseyKorshuk/thin-plate-spline-motion-model/tree/main/checkpoints)).
Pick the checkpoint that matches your use case:

- `vox.pth.tar` + `config/vox-256.yaml` -- talking-head / portrait motion
- `taichi.pth.tar` + `config/taichi-256.yaml` -- full-body motion

Place it at `checkpoints/<name>.pth.tar` inside the repo, then point
Sigma-Animation at it:

```bash
export TPSMM_REPO=/path/to/Thin-Plate-Spline-Motion-Model
export TPSMM_CONFIG=/path/to/Thin-Plate-Spline-Motion-Model/config/vox-256.yaml
export TPSMM_CHECKPOINT=/path/to/Thin-Plate-Spline-Motion-Model/checkpoints/vox.pth.tar
export TPSMM_PYTHON=python3   # or a venv's python with the deps above installed
export SIGMA_DEFAULT_BACKEND=tpsmm
```

`GET /api/backends` will list `tpsmm` once the repo, config, checkpoint, and
python executable are all found on disk (see `TPSMMBackend.is_available`).

Note: outbound access to the checkpoint hosts above depends on your network
policy -- some sandboxed environments (including hosted Claude Code
sessions) allow `github.com`/`pypi.org` but block `huggingface.co` and
Google/Baidu file hosts. Download the checkpoint from a machine that can
reach them, then copy it to wherever the backend runs.

## Wan-Animate-2 (GPU, production quality)

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
