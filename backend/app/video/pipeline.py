"""Removal pipeline: sampling, per-mode preparation, streaming render.

Everything here is a plain function of (paths, params) so it can be called from
an in-process thread pool today and from an RQ worker later.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .alpha import AlphaModel, estimate_alpha_model, remove_alpha
from .crop import CropPlan, apply_crop, plan_crop
from .detection import Box, Detection, detect_watermark, logo_mask
from .ffmpeg_io import FrameReader, FrameWriter, VideoInfo
from .inpaint import TemporalInpainter, inpaint_fast

log = logging.getLogger(__name__)

Mode = Literal["alpha", "inpaint_fast", "inpaint_temporal", "crop"]
MODES: tuple[str, ...] = ("alpha", "inpaint_fast", "inpaint_temporal", "crop")

ProgressFn = Callable[[float], None]


@dataclass(frozen=True)
class RenderParams:
    mode: Mode
    box: Box
    high_quality: bool = False

    def cache_key(self) -> str:
        """Samples, mask and alpha depend only on the box, so all modes share them."""
        raw = json.dumps(self.box.to_dict(), sort_keys=True)
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Sampling
# --------------------------------------------------------------------------- #


def _sample_vf(info: VideoInfo, n: int) -> str:
    n = max(2, min(n, info.nb_frames))
    rate = n / max(info.duration, 1e-3)
    return f"fps={rate:.6f}"


def sample_frames(path: str | Path, info: VideoInfo, n: int = 40, max_dim: int = 640) -> tuple[np.ndarray, float]:
    """Evenly spaced, downscaled frames for detection. Returns (frames, scale)."""
    scale = min(1.0, max_dim / max(info.width, info.height))
    sw, sh = max(2, round(info.width * scale)), max(2, round(info.height * scale))
    vf = f"{_sample_vf(info, n)},scale={sw}:{sh}"
    frames = np.stack(list(FrameReader(path, info, vf=vf, out_size=(sw, sh))))
    return frames, scale


def sample_rois(path: str | Path, info: VideoInfo, roi: Box, n: int = 32) -> np.ndarray:
    """Evenly spaced full-resolution crops of ``roi`` (ffmpeg does the crop)."""
    # Convert to BGR *before* cropping: on subsampled YUV, ffmpeg's crop rounds
    # odd offsets/sizes to the chroma grid, which would skew our raw frames.
    vf = f"{_sample_vf(info, n)},format=bgr24,crop={roi.w}:{roi.h}:{roi.x}:{roi.y}:exact=1"
    return np.stack(list(FrameReader(path, info, vf=vf, out_size=(roi.w, roi.h))))


def detect(path: str | Path, info: VideoInfo) -> Detection:
    frames, scale = sample_frames(path, info)
    det = detect_watermark(frames)
    box = det.box.scale(1 / scale, 1 / scale).clamp(info.width, info.height)
    return Detection(box, det.confidence, det.corner, det.auto)


def grab_frame(path: str | Path, info: VideoInfo, t: float) -> np.ndarray:
    for frame in FrameReader(path, info, start=t):
        return frame.copy()
    raise RuntimeError("Could not decode a frame")


# --------------------------------------------------------------------------- #
# Processors (one per mode)
# --------------------------------------------------------------------------- #


class FrameProcessor:
    """Turns a window of consecutive full frames into one cleaned centre frame."""

    window_radius = 0

    def process(self, window: Sequence[np.ndarray], center: int) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class _RoiProcessor(FrameProcessor):
    def __init__(self, roi: Box):
        self.roi = roi

    def _paste(self, frame: np.ndarray, roi_img: np.ndarray) -> np.ndarray:
        out = frame.copy()
        out[self.roi.slices] = roi_img
        return out


class AlphaProcessor(_RoiProcessor):
    def __init__(self, roi: Box, model: AlphaModel, alpha_max: float = 0.85):
        super().__init__(roi)
        self.model, self.alpha_max = model, alpha_max
        _, fallback = remove_alpha(np.zeros((*model.alpha.shape, 3), np.uint8), model, alpha_max)
        # Inpaint a slightly grown region around near-opaque pixels.
        self.fallback = cv2.dilate(fallback, np.ones((5, 5), np.uint8)) if fallback.any() else fallback

    def process(self, window, center):
        frame = window[center]
        restored, _ = remove_alpha(frame[self.roi.slices], self.model, self.alpha_max)
        if self.fallback.any():
            restored = inpaint_fast(restored, self.fallback)
        return self._paste(frame, restored)


class FastInpaintProcessor(_RoiProcessor):
    def __init__(self, roi: Box, mask: np.ndarray):
        super().__init__(roi)
        self.mask = mask

    def process(self, window, center):
        frame = window[center]
        return self._paste(frame, inpaint_fast(frame[self.roi.slices], self.mask))


class TemporalInpaintProcessor(_RoiProcessor):
    def __init__(self, roi: Box, mask: np.ndarray, radius: int = 2):
        super().__init__(roi)
        self.window_radius = radius
        self.inpainter = TemporalInpainter(mask, radius=radius)

    def process(self, window, center):
        rois = [f[self.roi.slices] for f in window]
        return self._paste(window[center], self.inpainter.process(rois, center))


class CropProcessor(FrameProcessor):
    def __init__(self, plan: CropPlan):
        self.plan = plan

    def process(self, window, center):
        return apply_crop(window[center], self.plan)


def processing_roi(box: Box, info: VideoInfo) -> Box:
    """Box plus context: needed for inpainting, flow and as variance reference."""
    pad = max(16, max(box.w, box.h) // 2)
    return box.pad(pad, info.width, info.height)


def prepare(path: str | Path, info: VideoInfo, params: RenderParams, cache_dir: Path | None = None) -> FrameProcessor:
    """Build the processor for ``params``.

    The sampled crops, logo mask and alpha model are cached per box, so switching
    modes (or rendering after previewing) never re-reads the video for them.
    """
    box = params.box.clamp(info.width, info.height)
    if params.mode == "crop":
        return CropProcessor(plan_crop(info.width, info.height, box))

    roi = processing_roi(box, info)
    key = params.cache_key()
    model_path = cache_dir / f"model-{key}.npz" if cache_dir else None
    samples_path = cache_dir / f"samples-{key}.npy" if cache_dir else None
    cached = dict(np.load(model_path)) if model_path and model_path.exists() else {}
    dirty = False
    rois: np.ndarray | None = None

    def samples() -> np.ndarray:
        nonlocal rois
        if rois is None:
            if samples_path and samples_path.exists():
                rois = np.load(samples_path)
            else:
                rois = sample_rois(path, info, roi)
                if samples_path:
                    np.save(samples_path, rois)
        return rois

    if "mask" not in cached:
        cached["mask"] = logo_mask(samples(), box.relative_to(roi), dilate_px=3)
        dirty = True
    if params.mode == "alpha" and "alpha" not in cached:
        fitted = estimate_alpha_model(samples(), cached["mask"])
        cached.update(alpha=fitted.alpha, color=fitted.color)
        dirty = True
    if model_path and dirty:
        np.savez(model_path, **cached)  # small; skip compression to save CPU

    mask = cached["mask"]
    if params.mode == "alpha":
        model = AlphaModel(cached["alpha"], cached["color"])
        log.info("alpha model: colour=%s max alpha=%.2f", model.color.round(1), float(model.alpha.max()))
        return AlphaProcessor(roi, model)
    if params.mode == "inpaint_fast":
        return FastInpaintProcessor(roi, mask)
    if params.mode == "inpaint_temporal":
        return TemporalInpaintProcessor(roi, mask)
    raise ValueError(f"Unknown mode {params.mode!r}")


# --------------------------------------------------------------------------- #
# Streaming
# --------------------------------------------------------------------------- #


def iter_windows(frames: Iterable[np.ndarray], radius: int) -> Iterator[tuple[list[np.ndarray], int]]:
    """Yield (window, centre index) for every frame, with ``radius`` neighbours each side.

    Windows are truncated at the start and end of the stream. Memory is bounded
    by 2 * radius + 1 frames.
    """
    buf: deque[np.ndarray] = deque()
    base = 0  # absolute index of buf[0]
    c = 0  # next centre to emit
    n = 0  # frames received

    def emit() -> tuple[list[np.ndarray], int]:
        lo, hi = max(base, c - radius), min(n - 1, c + radius)
        return [buf[k - base] for k in range(lo, hi + 1)], c - lo

    for frame in frames:
        buf.append(frame)
        n += 1
        while c + radius <= n - 1:
            yield emit()
            c += 1
            while base < c - radius:
                buf.popleft()
                base += 1
    while c < n:
        yield emit()
        c += 1
        while base < c - radius:
            buf.popleft()
            base += 1


def process_stream(frames: Iterable[np.ndarray], proc: FrameProcessor) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (original, cleaned) frame pairs."""
    for window, center in iter_windows(frames, proc.window_radius):
        yield window[center], proc.process(window, center)


def render(src: str | Path, out: str | Path, info: VideoInfo, proc: FrameProcessor, high_quality: bool = False,
           start: float | None = None, duration: float | None = None,
           progress: ProgressFn | None = None, preset: str | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    """Encode the cleaned video. Returns the (before, after) pair from the middle frame."""
    total = info.nb_frames if duration is None else max(1, round(duration * info.fps_float))
    middle, still = total // 2, None
    with FrameWriter(out, src, info, high_quality=high_quality, start=start, duration=duration, preset=preset) as writer:
        for i, (orig, clean) in enumerate(process_stream(FrameReader(src, info, start=start, duration=duration), proc)):
            writer.write(clean)
            if i == middle:
                still = (orig.copy(), clean.copy())
            if progress and i % 5 == 0:
                progress(min(i / total, 0.99))
    if progress:
        progress(1.0)
    return still
