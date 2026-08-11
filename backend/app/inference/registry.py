from __future__ import annotations

from .base import AnimationBackend
from .mock import MockAnimationBackend
from .wan_animate2 import WanAnimate2Backend

_BACKENDS: dict[str, type[AnimationBackend]] = {
    "mock": MockAnimationBackend,
    "wan-animate-2": WanAnimate2Backend,
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
