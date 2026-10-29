"""Synthetic test video: moving backgrounds with a known logo composited on top."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class SyntheticVideo:
    clean: np.ndarray  # (N, H, W, 3) uint8 ground-truth backgrounds
    observed: np.ndarray  # (N, H, W, 3) uint8 watermarked frames
    alpha: np.ndarray  # (H, W) float32 ground-truth opacity
    color: np.ndarray  # (3,) float32 BGR
    logo_box: tuple[int, int, int, int]  # x, y, w, h (tight)


def sparkle_alpha(h: int, w: int, cx: float, cy: float, r: float, peak: float) -> np.ndarray:
    """Four-pointed star with soft (anti-aliased) edges, like a sparkle logo."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = np.abs(xx - cx) / r, np.abs(yy - cy) / r
    # Astroid-like star: |x|^0.5 + |y|^0.5 <= 1
    d = np.sqrt(dx) + np.sqrt(dy)
    a = np.clip((1.0 - d) * 6.0, 0.0, 1.0) * peak
    return a.astype(np.float32)


def moving_background(n: int, h: int, w: int, seed: int = 0, speed: float = 3.0) -> np.ndarray:
    """Smooth colour gradients + drifting texture + a moving blob."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    frames = []
    for t in range(n):
        phase = t * speed
        b = 90 + 60 * np.sin((xx + phase) / 37.0) * np.cos(yy / 29.0)
        g = 110 + 70 * np.sin((yy - 0.7 * phase) / 23.0 + t * 0.05)
        r = 130 + 50 * np.cos((xx * 0.6 + yy * 0.4 + 1.3 * phase) / 41.0)
        img = np.stack([b, g, r], -1)
        # Moving dark blob so some frames put strong contrast under the logo.
        bx, by = (w * 0.2 + phase * 2.0) % w, h * 0.5 + 0.35 * h * np.sin(t / 7.0)
        blob = np.exp(-(((xx - bx) ** 2 + (yy - by) ** 2) / (2 * (0.12 * h) ** 2)))
        img = img * (1 - 0.6 * blob[..., None])
        img += rng.normal(0, 1.0, img.shape)  # sensor-ish noise
        frames.append(np.clip(img, 0, 255).astype(np.uint8))
    return np.stack(frames)


def make_video(n: int = 48, h: int = 180, w: int = 320, peak: float = 0.5,
               color=(255.0, 255.0, 255.0), seed: int = 0) -> SyntheticVideo:
    clean = moving_background(n, h, w, seed)
    r = 0.07 * w
    cx, cy = w - 0.06 * w - r, h - 0.08 * h - r
    alpha = sparkle_alpha(h, w, cx, cy, r, peak)
    color = np.asarray(color, np.float32)
    a = alpha[None, ..., None]
    observed = np.clip((1 - a) * clean + a * color + 0.5, 0, 255).astype(np.uint8)
    ys, xs = np.nonzero(alpha > 0)
    box = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
    return SyntheticVideo(clean, observed, alpha, color, box)


def psnr(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    a, b = a.astype(np.float64), b.astype(np.float64)
    if mask is not None:
        m = np.broadcast_to(mask.astype(bool)[..., None], a.shape[-3:])
        m = np.broadcast_to(m, a.shape)
        a, b = a[m], b[m]
    mse = np.mean((a - b) ** 2)
    return float("inf") if mse == 0 else 10 * np.log10(255.0**2 / mse)


def translating_texture(n: int, h: int, w: int, dx: float = 2.0, seed: int = 1) -> np.ndarray:
    """Textured scene panning horizontally: ideal for temporal inpainting."""
    rng = np.random.default_rng(seed)
    big = rng.integers(0, 255, (h, w + int(n * dx) + 8, 3)).astype(np.uint8)
    big = cv2.GaussianBlur(big, (0, 0), 2.5)
    big = cv2.normalize(big, None, 0, 255, cv2.NORM_MINMAX)
    return np.stack([big[:, int(round(t * dx)): int(round(t * dx)) + w] for t in range(n)])
