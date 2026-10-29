"""Alpha-estimation maths on a synthetic video with a known logo."""

import cv2
import numpy as np
import pytest

from app.video.alpha import AlphaModel, estimate_alpha_model, fit_alpha, remove_alpha
from tests.synthetic import make_video, psnr


def _logo_mask(alpha: np.ndarray, grow: int = 3) -> np.ndarray:
    m = (alpha > 0).astype(np.uint8) * 255
    return cv2.dilate(m, np.ones((2 * grow + 1, 2 * grow + 1), np.uint8))


@pytest.mark.parametrize("color", [(255, 255, 255), (40, 180, 220)])
def test_fit_alpha_with_known_background_is_exact(color):
    """With the true background the least-squares fit must recover a and L."""
    v = make_video(color=color)
    mask = _logo_mask(v.alpha)
    model = fit_alpha(v.observed.astype(np.float32), v.clean.astype(np.float32), mask > 0)

    # Only 8-bit rounding noise remains.
    err = np.abs(model.alpha - v.alpha)[mask > 0]
    assert err.mean() < 0.005
    assert err.max() < 0.05
    assert np.allclose(model.color, color, atol=2.0)


def test_reverse_blend_formula_roundtrip():
    """original = (observed - a*L) / (1 - a) inverts the compositing exactly."""
    rng = np.random.default_rng(0)
    clean = rng.integers(0, 256, (32, 32, 3)).astype(np.uint8)
    alpha = rng.uniform(0, 0.8, (32, 32)).astype(np.float32)
    color = np.array([250, 240, 230], np.float32)
    a = alpha[..., None]
    observed = np.clip((1 - a) * clean + a * color + 0.5, 0, 255).astype(np.uint8)

    restored, fallback = remove_alpha(observed, AlphaModel(alpha, color), alpha_max=0.85)
    assert not fallback.any()
    # Rounding error is amplified by 1/(1-a) <= 5x.
    assert np.abs(restored.astype(int) - clean.astype(int)).max() <= 4


def test_near_opaque_pixels_are_flagged_for_fallback():
    alpha = np.full((4, 4), 0.95, np.float32)
    alpha[0, 0] = 0.2
    _, fallback = remove_alpha(np.zeros((4, 4, 3), np.uint8), AlphaModel(alpha, np.full(3, 255, np.float32)))
    assert fallback[0, 0] == 0
    assert (fallback.ravel()[1:] == 255).all()


def test_end_to_end_estimation_psnr():
    """Blind estimate (inpainted backgrounds) -> recovery PSNR in the masked region."""
    v = make_video()
    mask = _logo_mask(v.alpha)
    model = estimate_alpha_model(v.observed, mask)

    assert np.allclose(model.color, 255, atol=20)

    region = v.alpha > 0.02
    restored = np.stack([remove_alpha(f, model)[0] for f in v.observed])
    before = psnr(v.observed, v.clean, region)
    after = psnr(restored, v.clean, region)
    print(f"masked-region PSNR: watermarked {before:.1f} dB -> restored {after:.1f} dB")
    assert after > 35.0
    assert after > before + 10.0
