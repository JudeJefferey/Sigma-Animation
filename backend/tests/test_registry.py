from app.inference.registry import _BACKENDS, get_backend


def test_all_backends_registered():
    assert set(_BACKENDS) == {"mock", "tpsmm", "wan-animate-2", "wan-ti2v"}


def test_get_backend_returns_correct_type():
    from app.inference.mock import MockAnimationBackend
    from app.inference.tpsmm import TPSMMBackend
    from app.inference.wan_animate2 import WanAnimate2Backend

    assert isinstance(get_backend("mock"), MockAnimationBackend)
    assert isinstance(get_backend("tpsmm"), TPSMMBackend)
    assert isinstance(get_backend("wan-animate-2"), WanAnimate2Backend)


def test_unavailable_backend_reports_unavailable(monkeypatch):
    monkeypatch.delenv("TPSMM_REPO", raising=False)
    backend = get_backend("tpsmm")
    assert backend.is_available() is False
