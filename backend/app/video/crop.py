"""Mode C: crop/scale fallback.

Cut away the band of the frame that contains the logo (a horizontal band at the
top/bottom or a vertical band at the left/right, whichever keeps more of the
picture), crop the other axis to restore the original aspect ratio, and scale
back to the original resolution. Lossless for the content that remains, but it
zooms in slightly and loses the edges.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .detection import Box


@dataclass(frozen=True)
class CropPlan:
    crop: Box  # region of the source frame to keep
    out_w: int
    out_h: int


def plan_crop(width: int, height: int, box: Box, margin: int = 4) -> CropPlan:
    aspect = width / height
    options: list[Box] = []

    # Option 1: drop a horizontal band (rows) containing the logo.
    if box.y + box.h / 2 >= height / 2:
        y0, y1 = 0, max(box.y - margin, 1)
    else:
        y0, y1 = min(box.y + box.h + margin, height - 1), height
    kh = y1 - y0
    kw = min(width, round(kh * aspect))
    options.append(Box((width - kw) // 2, y0, kw, kh))

    # Option 2: drop a vertical band (columns) containing the logo.
    if box.x + box.w / 2 >= width / 2:
        x0, x1 = 0, max(box.x - margin, 1)
    else:
        x0, x1 = min(box.x + box.w + margin, width - 1), width
    kw = x1 - x0
    kh = min(height, round(kw / aspect))
    # Keep the rows furthest from the logo's edge.
    y = 0 if box.y + box.h / 2 >= height / 2 else height - kh
    options.append(Box(x0, y, kw, kh))

    best = max(options, key=lambda b: b.w * b.h)
    return CropPlan(best.clamp(width, height), width, height)


def apply_crop(frame: np.ndarray, plan: CropPlan) -> np.ndarray:
    ys, xs = plan.crop.slices
    return cv2.resize(frame[ys, xs], (plan.out_w, plan.out_h), interpolation=cv2.INTER_LANCZOS4)
