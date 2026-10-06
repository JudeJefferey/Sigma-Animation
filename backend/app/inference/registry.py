from __future__ import annotations

from .base import AnimationBackend
from .mock import MockAnimationBackend
from .tpsmm import TPSMMBackend
from .wan_animate2 import WanAnimate2Backend
from .wan_ti2v import WanTI2VBackend

_BACKENDS: dict[str, type[AnimationBackend]] = {
    "mock": MockAnimationBackend,
    "tpsmm": TPSMMBackend,
    "wan-animate-2": WanAnimate2Backend,
    "wan-ti2v": WanTI2VBackend,
}


def get_backend(name: str) -> AnimationBackend:
    try:
        backend_cls = _BACKENDS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown animation backend '{name}'. Available: {sorted(_BACKENDS)}"
        ) from exc
    return backend_cls()


def available_backends() -> list[str]:
    return [name for name, cls in _BACKENDS.items() if cls().is_available()]


def backend_info() -> list[dict]:
    """Every registered engine with whether it is usable on this deployment."""
    info = []
    for name, cls in _BACKENDS.items():
        backend = cls()
        info.append({
            "name": name,
            "description": backend.description,
            "available": backend.is_available(),
            "modes": sorted(backend.modes),
            "max_clip_seconds": backend.max_clip_seconds,
        })
    return info
