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

from .inpaint import inpaint_fast

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


def estimate_backgrounds(rois: np.ndarray, mask: np.ndarray, radius: int = 3) -> np.ndarray:
    """Spatially inpaint the masked area of each sampled ROI -> B^_t (float32)."""
    return np.stack([inpaint_fast(r, mask, radius) for r in rois]).astype(np.float32)


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

    Every quantity the three stages need is a weighted temporal moment of I and
    B (means, E[B·B], E[I·B]). Those are computed once, over masked pixels only,
    so each refinement iteration below is just a few per-pixel dot products.
    """
    m = mask.astype(bool)
    n = observed.shape[0]
    I = observed[:, m].astype(np.float64)  # (N, P, 3) — masked pixels only
    B = background[:, m].astype(np.float64)
    w = np.ones(n) if weights is None else np.asarray(weights, np.float64)
    w = w / w.sum()

    # Weighted temporal moments, per pixel (P,) or per pixel and channel (P, 3).
    I_mean = np.einsum("n,npc->pc", w, I)
    B_mean = np.einsum("n,npc->pc", w, B)
    E_BB = np.einsum("n,npc,npc->p", w, B, B)
    E_IB = np.einsum("n,npc,npc->p", w, I, B)
    del I, B

    # ---- Stage 1: per-pixel regression I = s * B + c_c (shared slope over channels)
    var_b = E_BB - (B_mean * B_mean).sum(1)
    cov = E_IB - (I_mean * B_mean).sum(1)
    slope = np.where(var_b > 1e-6, cov / np.maximum(var_b, 1e-6), 1.0)
    a1 = np.clip(1.0 - slope, 0.0, 1.0)
    intercept = I_mean - slope[:, None] * B_mean  # (P, 3) = a * L

    # Colour from well-conditioned pixels: background varied (std > ~6 levels)
    # and a clearly visible but not opaque logo.
    good = (var_b > 36.0) & (a1 > 0.1) & (a1 < 0.95)
    if good.sum() >= 5:
        color = np.median(intercept[good] / a1[good][:, None], axis=0)
    else:
        color = np.asarray(default_color, np.float64)
    color = np.clip(color, 0.0, 255.0)

    d_mean = I_mean - B_mean  # E[I - B]
    a = np.zeros(len(var_b))
    for _ in range(max(n_iter, 1)):
        # ---- Stage 2: alpha given colour (closed form, per pixel)
        #   num = E[(I-B)·(L-B)] = L·E[I-B] - (E[I·B] - E[B·B])
        #   den = E[|L-B|^2]     = |L|^2 - 2 L·E[B] + E[B·B]
        num = d_mean @ color - (E_IB - E_BB)
        den = color @ color - 2.0 * (B_mean @ color) + E_BB
        a = np.clip(np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0.0), 0.0, 1.0)

        # ---- Stage 3: colour given alpha, LS over all logo pixels and frames
        #   L = sum_p a_p (E[I]_p - (1 - a_p) E[B]_p) / sum_p a_p^2
        sel = a > 0.1
        if sel.sum() < 5:
            break
        a_s = a[sel][:, None]
        num_c = (a_s * (I_mean[sel] - (1.0 - a_s) * B_mean[sel])).sum(0)
        color = np.clip(num_c / max(float((a_s * a_s).sum()), 1e-9), 0.0, 255.0)

    alpha = np.zeros(m.shape, np.float32)
    alpha[m] = a
    alpha[alpha < ALPHA_EPS] = 0.0
    return AlphaModel(alpha, color.astype(np.float32))


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
    a = model.alpha
    restored = frame.copy()
    # Only pixels the logo actually touches need the (float) inversion.
    sel = (a > 0) & (a < alpha_max)
    if sel.any():
        av = a[sel][:, None]
        inv = (frame[sel].astype(np.float32) - av * model.color) / (1.0 - av)
        restored[sel] = np.clip(inv + 0.5, 0, 255).astype(np.uint8)
    fallback = ((a >= alpha_max) * 255).astype(np.uint8)
    return restored, fallback
