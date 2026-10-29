"""Watermark localisation.

A visible overlay watermark is *static*: it sits at the same pixels in every
frame while the content underneath it moves. We exploit that with two cues
computed over a sparse sample of frames:

1. Persistent edges. The gradient magnitude of the temporal *median* frame keeps
   only structure that is present in most frames. Moving content averages out;
   the logo's outline survives. Dividing by the mean per-frame gradient gives a
   "persistence" ratio that is ~1 for static edges and < 1 for moving ones.
2. Low temporal variance. Under a semi-transparent overlay the background
   variance is attenuated by (1 - alpha)^2, so the logo region is quieter than
   its surroundings.

The combined score map is searched in each corner (the logo lives in a corner,
bottom-right by default) and the strongest compact blob wins. No pixel
positions are hard-coded; if nothing convincing is found we fall back to a box
proportional to the frame size, which the user can then adjust in the UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

CORNERS = ("bottom-right", "bottom-left", "top-right", "top-left")


@dataclass(frozen=True)
class Box:
    """Axis-aligned rectangle in pixel coordinates (x, y = top-left)."""

    x: int
    y: int
    w: int
    h: int

    def clamp(self, width: int, height: int) -> "Box":
        x = int(np.clip(self.x, 0, max(width - 1, 0)))
        y = int(np.clip(self.y, 0, max(height - 1, 0)))
        w = int(np.clip(self.w, 1, width - x))
        h = int(np.clip(self.h, 1, height - y))
        return Box(x, y, w, h)

    def pad(self, px: int, width: int, height: int) -> "Box":
        return Box(self.x - px, self.y - px, self.w + 2 * px, self.h + 2 * px).clamp(width, height)

    def scale(self, sx: float, sy: float) -> "Box":
        return Box(round(self.x * sx), round(self.y * sy), round(self.w * sx), round(self.h * sy))

    def relative_to(self, outer: "Box") -> "Box":
        """Express this box in the coordinate frame of ``outer``."""
        return Box(self.x - outer.x, self.y - outer.y, self.w, self.h)

    @property
    def slices(self) -> tuple[slice, slice]:
        return slice(self.y, self.y + self.h), slice(self.x, self.x + self.w)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Box":
        return cls(int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))


@dataclass
class Detection:
    box: Box
    confidence: float  # 0..1, how much the winning blob stands out
    corner: str
    auto: bool  # False when we fell back to the proportional default box

    def to_dict(self) -> dict:
        return {"box": self.box.to_dict(), "confidence": self.confidence, "corner": self.corner, "auto": self.auto}


def default_box(width: int, height: int, corner: str = "bottom-right") -> Box:
    """Proportional guess for where a corner logo sits. Never pixel-exact by design."""
    w, h = round(width * 0.12), round(height * 0.09)
    mx, my = round(width * 0.015), round(height * 0.02)
    x = width - w - mx if "right" in corner else mx
    y = height - h - my if "bottom" in corner else my
    return Box(x, y, w, h).clamp(width, height)


# --------------------------------------------------------------------------- #
# Score map
# --------------------------------------------------------------------------- #


def _to_gray_stack(frames: np.ndarray) -> np.ndarray:
    if frames.ndim == 4:
        # BGR -> luma without a Python loop.
        frames = frames[..., 0] * 0.114 + frames[..., 1] * 0.587 + frames[..., 2] * 0.299
    return frames.astype(np.float32)


def _grad_mag(img: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def static_overlay_score(frames: np.ndarray) -> np.ndarray:
    """Per-pixel likelihood (0..1) that a pixel belongs to a static overlay.

    ``frames`` is (N, H, W) or (N, H, W, 3) uint8/float. N >= 2.
    """
    gray = _to_gray_stack(frames)
    median = np.median(gray, axis=0)
    std = gray.std(axis=0)

    e_med = _grad_mag(median)
    e_mean = np.mean([_grad_mag(g) for g in gray], axis=0)

    # ~1 where the same edge is present in every frame; small where edges move.
    persistence = np.clip(e_med / (e_mean + 1e-3), 0.0, 1.0)
    # Edge strength, normalised robustly so a few hot pixels don't dominate.
    strength = np.clip(e_med / (np.percentile(e_med, 99.5) + 1e-6), 0.0, 1.0)
    # Quieter than the typical pixel -> more likely under an overlay.
    quiet = 1.0 / (1.0 + std / (np.median(std) + 1.0))

    return (strength * persistence**2 * quiet).astype(np.float32)


# --------------------------------------------------------------------------- #
# Blob search
# --------------------------------------------------------------------------- #


def _corner_region(width: int, height: int, corner: str, frac: float) -> Box:
    rw, rh = round(width * frac), round(height * frac)
    x = width - rw if "right" in corner else 0
    y = height - rh if "bottom" in corner else 0
    return Box(x, y, rw, rh)


def _otsu_threshold(score: np.ndarray) -> float:
    u8 = np.clip(score / (score.max() + 1e-6) * 255, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(t) / 255.0 * float(score.max())


def _best_blob(score: np.ndarray, link_px: int) -> tuple[Box | None, float, float]:
    """Return the strongest compact blob in ``score``, its total mass and its mean score."""
    if score.max() <= 1e-6:
        return None, 0.0, 0.0
    thr = max(_otsu_threshold(score), 0.15 * float(score.max()))
    binary = (score >= thr).astype(np.uint8)
    # Close small gaps so the logo's glyphs (e.g. sparkle + wordmark) merge.
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (link_px | 1, link_px | 1))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return None, 0.0, 0.0
    rh, rw = score.shape
    min_area = max(4, int(0.0005 * score.size))
    best_mass, best, best_mean = 0.0, None, 0.0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        # A logo is small relative to the search region; region-sized blobs are
        # static background or noise, not an overlay.
        if w > 0.7 * rw or h > 0.7 * rh:
            continue
        # Score only the pixels that passed the threshold (not the closed gaps).
        px = score[(labels == i) & (score >= thr)]
        mass = float(px.sum())
        # Penalise long thin blobs (horizon lines, letterbox edges).
        aspect = max(w, h) / max(min(w, h), 1)
        if aspect > 8:
            mass *= 0.2
        if mass > best_mass:
            best_mass, best, best_mean = mass, Box(int(x), int(y), int(w), int(h)), float(px.mean())
    return best, best_mass, best_mean


def detect_watermark(
    frames: np.ndarray,
    corner_prior: str = "bottom-right",
    region_frac: float = 0.3,
    min_confidence: float = 0.25,
) -> Detection:
    """Locate a static corner overlay in a stack of sampled frames.

    ``frames`` may be downscaled for speed; the returned box is in the same
    coordinate system as ``frames``. Scale it back with :meth:`Box.scale`.
    """
    _, height, width = frames.shape[:3]
    score = static_overlay_score(frames)
    link_px = max(3, round(0.02 * max(width, height)))
    # Typical score of the frame, used as the contrast reference for every corner.
    frame_ref = float(np.percentile(score, 75)) + 1e-3

    candidates: list[tuple[float, float, str, Box]] = []
    for corner in CORNERS:
        region = _corner_region(width, height, corner, region_frac)
        sub = score[region.slices]
        blob, mass, blob_mean = _best_blob(sub, link_px)
        if blob is None:
            continue
        box = Box(blob.x + region.x, blob.y + region.y, blob.w, blob.h)
        # Contrast of the blob's pixels against both the rest of its corner and
        # the frame as a whole (whichever is stronger), so a uniformly "static"
        # corner can't score highly against itself.
        outside = np.ones(sub.shape, bool)
        outside[blob.slices] = False
        local = float(sub[outside].mean()) if outside.any() else float(sub.mean())
        ratio = blob_mean / max(local + 1e-6, frame_ref)
        confidence = float(1.0 - np.exp(-max(ratio - 1.0, 0.0) / 4.0))
        rank = mass * confidence * (1.25 if corner == corner_prior else 1.0)
        candidates.append((rank, confidence, corner, box))

    if candidates:
        _, confidence, corner, box = max(candidates, key=lambda c: c[0])
        if confidence >= min_confidence:
            pad = max(2, round(0.08 * max(box.w, box.h)))
            return Detection(box.pad(pad, width, height), round(confidence, 3), corner, auto=True)
        fallback_conf = confidence
    else:
        fallback_conf = 0.0

    return Detection(default_box(width, height, corner_prior), round(fallback_conf, 3), corner_prior, auto=False)


# --------------------------------------------------------------------------- #
# Per-pixel logo mask inside a (possibly user-adjusted) box
# --------------------------------------------------------------------------- #


def _fill_holes(binary: np.ndarray) -> np.ndarray:
    """Fill enclosed holes so an outlined glyph becomes a solid mask."""
    # Pad with background so the flood seed is guaranteed to be outside the glyph.
    flood = np.pad(binary, 1).astype(np.uint8)
    ff_mask = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8)
    cv2.floodFill(flood, ff_mask, (0, 0), 1)
    holes = (flood[1:-1, 1:-1] == 0).astype(np.uint8)
    return binary | holes


def logo_mask(rois: np.ndarray, box_in_roi: Box, dilate_px: int = 3) -> np.ndarray:
    """Binary uint8 mask (0/255) of the logo pixels, in ROI coordinates.

    ``rois`` is (N, h, w, 3): sampled crops of a region that contains the box
    plus some surrounding background (used as a variance reference).
    """
    n, h, w = rois.shape[:3]
    mask = np.zeros((h, w), np.uint8)
    ys, xs = box_in_roi.slices

    score = static_overlay_score(rois)
    sub = score[ys, xs]
    edge = np.zeros_like(sub, np.uint8)
    if sub.max() > 1e-6:
        edge = (sub >= max(_otsu_threshold(sub), 0.1 * float(sub.max()))).astype(np.uint8)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        edge = _fill_holes(cv2.morphologyEx(edge, cv2.MORPH_CLOSE, k))

    # Variance cue: std under the overlay is (1 - alpha) * std of the background.
    gray = _to_gray_stack(rois)
    std = gray.std(axis=0)
    outside = np.ones((h, w), bool)
    outside[ys, xs] = False
    ref = float(np.median(std[outside])) if outside.any() else float(np.median(std))
    quiet = np.zeros_like(edge)
    if ref > 2.0:  # only meaningful when the background actually moves
        quiet = (std[ys, xs] < 0.75 * ref).astype(np.uint8)
        quiet = cv2.morphologyEx(quiet, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # Contrast cue: the overlay shifts the colour of whatever is under it. Fill
    # the box in the median frame from its surroundings and flag pixels that
    # differ. Unlike the cues above this needs no motion, so a logo over a
    # static background (sky, wall, title card) is still covered completely.
    median = np.median(rois, axis=0).astype(np.uint8)
    box_mask = np.zeros((h, w), np.uint8)
    box_mask[ys, xs] = 255
    surround = cv2.inpaint(median, box_mask, 3, cv2.INPAINT_TELEA)
    diff = np.abs(median.astype(np.int16) - surround.astype(np.int16)).max(axis=2)[ys, xs]
    contrast = (diff > 8).astype(np.uint8)
    contrast = cv2.morphologyEx(contrast, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    inner = edge | quiet | contrast
    if inner.any():
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        inner = _fill_holes(cv2.morphologyEx(inner, cv2.MORPH_CLOSE, k))
    if inner.sum() < 0.05 * inner.size:
        inner[:] = 1  # nothing convincing: treat the whole box as the logo
    mask[ys, xs] = inner * 255

    if dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
        mask = cv2.dilate(mask, k)
    return mask
