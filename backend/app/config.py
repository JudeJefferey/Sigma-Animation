from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Runtime configuration, entirely local -- no third-party AI API keys."""

    data_dir: Path = Path(os.environ.get("SIGMA_DATA_DIR", "./data"))
    database_path: Path = Path(os.environ.get("SIGMA_DB_PATH", "./data/sigma_animation.db"))

    default_backend: str = os.environ.get("SIGMA_DEFAULT_BACKEND", "mock")

    wan_animate2_repo: str | None = os.environ.get("WAN_ANIMATE2_REPO")
    wan_animate2_config: str = os.environ.get("WAN_ANIMATE2_CONFIG", "./wan_animate_2.yaml")
    wan_animate2_python: str = os.environ.get("WAN_ANIMATE2_PYTHON", "python")
    wan_animate2_num_gpus: int = int(os.environ.get("WAN_ANIMATE2_NUM_GPUS", "1"))

    tpsmm_repo: str | None = os.environ.get("TPSMM_REPO")
    tpsmm_config: str | None = os.environ.get("TPSMM_CONFIG")
    tpsmm_checkpoint: str | None = os.environ.get("TPSMM_CHECKPOINT")
    tpsmm_python: str = os.environ.get("TPSMM_PYTHON", "python3")
    tpsmm_mode: str = os.environ.get("TPSMM_MODE", "relative")
    tpsmm_img_shape: str = os.environ.get("TPSMM_IMG_SHAPE", "256,256")

    wan_ti2v_repo: str | None = os.environ.get("WAN_TI2V_REPO")
    wan_ti2v_ckpt_dir: str | None = os.environ.get("WAN_TI2V_CKPT_DIR")
    wan_ti2v_python: str = os.environ.get("WAN_TI2V_PYTHON", "python")
    wan_ti2v_offload: bool = os.environ.get("WAN_TI2V_OFFLOAD", "true").lower() in ("1", "true", "yes")

    max_upload_mb: int = int(os.environ.get("SIGMA_MAX_UPLOAD_MB", "200"))
    max_output_fps: int = int(os.environ.get("SIGMA_MAX_OUTPUT_FPS", "120"))
    max_clip_seconds: int = int(os.environ.get("SIGMA_MAX_CLIP_SECONDS", "60"))

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"


settings = Settings()
