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

    max_upload_mb: int = int(os.environ.get("SIGMA_MAX_UPLOAD_MB", "200"))

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"


settings = Settings()
