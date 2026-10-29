"""Mode A: reverse alpha blending.

An overlay watermark is composited as

    I_t(p) = (1 - a(p)) * B_t(p) + a(p) * L

where I is the observed pixel, B the clean background, a the per-pixel opacity
of the logo and L its (single) colour. a and L are constant over time; B varies.

We don't know B_t under the logo, but we can get a decent estimate B^_t by
spatially inpainting each sampled frame from the logo's surroundings. With
that, estimation is linear least squares:

* Stage 1 (per pixel, across frames): regress I on B^. Slope = 1 - a,
  intercept = a * L. This needs the background to *vary* over time, and gives
  us a colour estimate L = intercept / a at well-conditioned pixels.
* Stage 2 (L fixed): a closed-form fit per pixel,
      a = sum w (I - B^)(L - B^) / sum w (L - B^)^2
  which only needs L != B^ and is far less sensitive to errors in B^ than the
  stage-1 slope (which suffers regression dilution).
* Stages 2 <-> 3 alternate a few times, re-solving L by least squares given a.

Recovery then inverts the blend: B = (I - a * L) / (1 - a). That division blows
up noise as a -> 1, so pixels above ``alpha_max`` are flagged for the
inpainting fallback (Mode B) instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Below this, a pixel is considered untouched by the logo.
ALPHA_EPS = 0.01


@dataclass
class AlphaModel:
    alpha: np.ndarray  # (h, w) float32 in [0, 1], ROI coordinates
    color: np.ndarray  # (3,) float32, BGR in [0, 255]

    def save(self, path: str) -> None:
        np.savez_compressed(path, alpha=self.alpha, color=self.color)

    @classmethod
    def load(cls, path: str) -> "AlphaModel":
        d = np.load(path)
        return cls(d["alpha"].astype(np.float32), d["color"].astype(np.float32))


def estimate_backgrounds(rois: np.ndarray, mask: np.ndarray, radius: int = 5) -> np.ndarray:
    """Spatially inpaint the masked area of each sampled ROI -> B^_t (float32)."""
    return np.stack([cv2.inpaint(r, mask, radius, cv2.INPAINT_TELEA) for r in rois]).astype(np.float32)


def frame_weights(rois: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Trust frames whose surroundings are smooth: inpainting is accurate there."""
    ring = cv2.dilate(mask, np.ones((9, 9), np.uint8)) & ~mask
    ring = ring > 0
    if not ring.any():
        return np.ones(len(rois), np.float32)
    w = []
    for r in rois:
        g = cv2.cvtColor(r, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
        w.append(1.0 / (1.0 + float(np.mean(cv2.magnitude(gx, gy)[ring])) / 10.0))
    return np.asarray(w, np.float32)


def fit_alpha(
    observed: np.ndarray,
    background: np.ndarray,
    mask: np.ndarray,
    weights: np.ndarray | None = None,
    n_iter: int = 3,
    default_color: tuple[float, float, float] = (255.0, 255.0, 255.0),
) -> AlphaModel:
    """Least-squares estimate of (alpha, colour) from frames and background estimates.

    observed, background: (N, h, w, 3) float. mask: (h, w) bool/uint8 — only
    pixels inside it are fitted, everything else gets alpha = 0.
    """
    I = observed.astype(np.float64)
    B = background.astype(np.float64)
    n = I.shape[0]
    m = mask.astype(bool)
    w = np.ones(n) if weights is None else np.asarray(weights, np.float64)
    w = (w / w.sum())[:, None, None, None]  # broadcast over (h, w, c)

    # ---- Stage 1: per-pixel regression I = s * B + c_c (shared slope over channels)
    I_mean = (w * I).sum(0)
    B_mean = (w * B).sum(0)
    dB = B - B_mean
    dI = I - I_mean
    var_b = (w * dB * dB).sum((0, 3))  # (h, w)
    cov = (w * dB * dI).sum((0, 3))
    slope = np.where(var_b > 1e-6, cov / np.maximum(var_b, 1e-6), 1.0)
    a1 = np.clip(1.0 - slope, 0.0, 1.0)
    intercept = I_mean - slope[..., None] * B_mean  # (h, w, 3) = a * L

    # Colour from well-conditioned pixels: background varied (std > ~6 levels)
    # and a clearly visible but not opaque logo.
    good = m & (var_b > 36.0) & (a1 > 0.1) & (a1 < 0.95)
    if good.sum() >= 5:
        color = np.median(intercept[good] / a1[good][:, None], axis=0)
    else:
        color = np.asarray(default_color, np.float64)
    color = np.clip(color, 0.0, 255.0)

    alpha = np.zeros(m.shape, np.float64)
    for _ in range(max(n_iter, 1)):
        # ---- Stage 2: alpha given colour (closed form, per pixel)
        d_obs = I - B
        d_logo = color[None, None, None, :] - B
        num = (w * d_obs * d_logo).sum((0, 3))
        den = (w * d_logo * d_logo).sum((0, 3))
        alpha = np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0.0)
        alpha = np.clip(alpha, 0.0, 1.0) * m

        # ---- Stage 3: colour given alpha, LS over all logo pixels and frames
        sel = m & (alpha > 0.1)
        if sel.sum() < 5:
            break
        a = alpha[None, ..., None]
        resid = I - (1.0 - a) * B  # = a * L
        num_c = (w * a * resid)[:, sel].sum((0, 1))
        den_c = (w * a * a)[:, sel].sum((0, 1))
        color = np.clip(num_c / np.maximum(den_c, 1e-9), 0.0, 255.0)

    alpha[alpha < ALPHA_EPS] = 0.0
    return AlphaModel(alpha.astype(np.float32), color.astype(np.float32))


def estimate_alpha_model(rois: np.ndarray, mask: np.ndarray) -> AlphaModel:
    """Convenience wrapper: inpaint backgrounds, weight frames, fit."""
    bgs = estimate_backgrounds(rois, mask)
    weights = frame_weights(rois, mask)
    return fit_alpha(rois.astype(np.float32), bgs, mask > 0, weights)


def remove_alpha(frame: np.ndarray, model: AlphaModel, alpha_max: float = 0.85) -> tuple[np.ndarray, np.ndarray]:
    """Invert the blend on a uint8 BGR ROI.

    Returns (restored uint8, fallback mask uint8 0/255). The fallback mask marks
    pixels where alpha >= alpha_max; those should be inpainted instead.
    """
    a = model.alpha[..., None]
    I = frame.astype(np.float32)
    safe = a < alpha_max
    restored = np.where(safe, (I - a * model.color) / np.maximum(1.0 - a, 1e-3), I)
    restored = np.clip(restored + 0.5, 0, 255).astype(np.uint8)
    fallback = ((model.alpha >= alpha_max) * 255).astype(np.uint8)
    return restored, fallback
