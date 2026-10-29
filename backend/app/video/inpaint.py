"""Mode B: inpainting.

* Fast: per-frame OpenCV Telea inpainting of the (dilated) logo mask.
* Temporal: the logo is static but the scene moves, so pixels hidden under the
  logo in frame t are often *visible* in a neighbouring frame. We estimate dense
  optical flow (Farneback) from frame t to each neighbour, warp the neighbour
  into t's geometry and copy over pixels that were unmasked in the neighbour.
  Whatever no neighbour can provide is filled spatially. Finally a light,
  motion-compensated blend with the previous output reduces flicker.

All work happens on a padded ROI around the logo, never on the full frame.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


def inpaint_fast(roi: np.ndarray, mask: np.ndarray, radius: int = 3) -> np.ndarray:
    """Telea inpainting on a uint8 BGR ROI with a 0/255 mask.

    Radius 3, not 2: on large logos over flat backgrounds radius 2 measured
    ~5 dB worse, while costing only ~40% less.
    """
    if not mask.any():
        return roi
    return cv2.inpaint(roi, mask, radius, cv2.INPAINT_TELEA)


def _fill_flow(flow: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace flow inside the mask by a smooth extrapolation of the flow around it.

    The static logo drags the estimated flow towards zero, so flow inside the
    mask can't be trusted. Normalised convolution: blur(flow * valid) / blur(valid).
    The blur is as wide as the logo, so it runs at 1/4 resolution: the result
    is a smooth field anyway, and this is >10x cheaper than blurring at full size.
    """
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return flow
    h, w = mask.shape
    s = 4 if min(h, w) >= 64 else 1
    sw, sh = max(1, w // s), max(1, h // s)
    valid = (mask == 0).astype(np.float32)
    small_valid = cv2.resize(valid, (sw, sh), interpolation=cv2.INTER_AREA)
    small_num = cv2.resize(flow * valid[..., None], (sw, sh), interpolation=cv2.INTER_AREA)
    sigma = max(int(np.ptp(ys)), int(np.ptp(xs)), 4) / 2.0 / s
    num = cv2.GaussianBlur(small_num, (0, 0), sigma)
    den = cv2.GaussianBlur(small_valid, (0, 0), sigma)[..., None]
    filled = cv2.resize(num / np.maximum(den, 1e-4), (w, h), interpolation=cv2.INTER_LINEAR)
    out = flow.copy()
    out[mask > 0] = filled[mask > 0]
    return out


class TemporalInpainter:
    """Stateful per-ROI temporal inpainter. Call :meth:`process` in frame order."""

    def __init__(self, mask: np.ndarray, radius: int = 2, smoothing: float = 0.3, max_warp_error: float = 12.0):
        self.mask = mask  # (h, w) uint8 0/255, ROI coordinates
        self.radius = radius
        self.smoothing = smoothing
        self.max_warp_error = max_warp_error  # mean abs error (0-255) on the ring
        h, w = mask.shape
        self._gx, self._gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        self._mask_f = (mask > 0).astype(np.float32)
        # Unmasked band around the logo, used to validate each warp.
        grown = cv2.dilate(mask, np.ones((11, 11), np.uint8))
        self._ring = (grown > 0) & (mask == 0)
        if not self._ring.any():
            self._ring = mask == 0
        # Soft edge for blending the smoothed result back in.
        self._feather = cv2.GaussianBlur(self._mask_f, (0, 0), 1.5)[..., None]
        self._prev_out: np.ndarray | None = None

    def _flow(self, src_gray: np.ndarray, dst_gray: np.ndarray) -> np.ndarray:
        # pyr_scale, levels, winsize, iterations, poly_n, poly_sigma, flags
        flow = cv2.calcOpticalFlowFarneback(src_gray, dst_gray, None, 0.5, 4, 21, 3, 5, 1.2, 0)
        return _fill_flow(flow, self.mask)

    def _warp(self, img: np.ndarray, flow: np.ndarray, border=cv2.BORDER_REPLICATE) -> np.ndarray:
        return cv2.remap(img, self._gx + flow[..., 0], self._gy + flow[..., 1], cv2.INTER_LINEAR, borderMode=border)

    def process(self, window: Sequence[np.ndarray], center: int) -> np.ndarray:
        """``window`` holds uint8 BGR ROIs of consecutive frames; returns the cleaned centre ROI."""
        cur = window[center]
        hole = self._mask_f > 0
        if not hole.any():
            return cur
        cur_gray = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)

        acc = np.zeros(cur.shape, np.float32)
        wsum = np.zeros(cur.shape[:2], np.float32)
        prev_flow = None
        for j, nb in enumerate(window):
            if j == center:
                continue
            flow = self._flow(cur_gray, cv2.cvtColor(nb, cv2.COLOR_BGR2GRAY))
            if j == center - 1:
                prev_flow = flow
            warped = self._warp(nb, flow).astype(np.float32)
            # A warped pixel is usable only if it landed on *unmasked* background
            # in the neighbour and inside its bounds.
            nb_mask = self._warp(self._mask_f, flow, border=cv2.BORDER_CONSTANT)
            fx = self._gx + flow[..., 0]
            fy = self._gy + flow[..., 1]
            inb = (fx >= 0) & (fx <= cur.shape[1] - 1) & (fy >= 0) & (fy <= cur.shape[0] - 1)
            ok = hole & (nb_mask < 0.01) & inb
            # Check the warp where we *can* see both frames: the ring around the
            # logo. A flow that fails there (large or complex motion) would paste
            # misaligned content, so down-weight or drop that neighbour.
            err = float(np.mean(np.abs(warped[self._ring] - cur[self._ring].astype(np.float32))))
            if err > self.max_warp_error:
                continue
            wt = ok.astype(np.float32) * float(np.exp(-err / 4.0)) / abs(j - center)
            acc += warped * wt[..., None]
            wsum += wt

        out = cur.astype(np.float32)
        got = wsum > 0
        out[got] = acc[got] / wsum[got][:, None]
        out = np.clip(out, 0, 255).astype(np.uint8)

        # Spatially fill whatever no neighbour could see.
        remaining = (hole & ~got).astype(np.uint8) * 255
        if remaining.any():
            # Inpaint using the temporally-filled pixels as extra known context.
            out = inpaint_fast(out, remaining)

        # Light motion-compensated temporal smoothing inside the mask only.
        if self._prev_out is not None and self.smoothing > 0:
            if prev_flow is None:
                prev_flow = self._flow(cur_gray, cv2.cvtColor(self._prev_out, cv2.COLOR_BGR2GRAY))
            prev_warped = self._warp(self._prev_out, prev_flow).astype(np.float32)
            blend = self._feather * self.smoothing
            out = np.clip(out * (1 - blend) + prev_warped * blend, 0, 255).astype(np.uint8)

        self._prev_out = out
        return out
