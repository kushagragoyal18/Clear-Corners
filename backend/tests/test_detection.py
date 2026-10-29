import numpy as np

from app.video.crop import plan_crop
from app.video.detection import Box, default_box, detect_watermark, logo_mask
from app.video.inpaint import TemporalInpainter, inpaint_fast
from app.video.pipeline import iter_windows
from tests.synthetic import make_video, psnr, sparkle_alpha, translating_texture


def _contains(outer: Box, x: int, y: int, w: int, h: int) -> bool:
    return outer.x <= x and outer.y <= y and outer.x + outer.w >= x + w and outer.y + outer.h >= y + h


def test_detects_bottom_right_logo():
    v = make_video()
    det = detect_watermark(v.observed)
    assert det.auto, det
    assert det.corner == "bottom-right"
    assert _contains(det.box, *v.logo_box), (det.box, v.logo_box)
    # Not absurdly larger than the logo either.
    assert det.box.w * det.box.h < 4 * v.logo_box[2] * v.logo_box[3]


def test_detects_logo_in_other_corner():
    v = make_video()
    flipped = v.observed[:, :, ::-1, :].copy()  # mirror horizontally: logo now bottom-left
    det = detect_watermark(flipped)
    assert det.corner == "bottom-left"


def test_falls_back_to_default_box_without_logo():
    v = make_video()
    det = detect_watermark(v.clean)
    assert not det.auto
    assert det.box == default_box(320, 180)


def test_logo_mask_covers_logo():
    v = make_video()
    x, y, w, h = v.logo_box
    box = Box(x, y, w, h).pad(4, 320, 180)
    roi = box.pad(30, 320, 180)
    rois = v.observed[:, roi.slices[0], roi.slices[1]]
    mask = logo_mask(rois, box.relative_to(roi))
    truth = v.alpha[roi.slices] > 0.05
    coverage = (mask[truth] > 0).mean()
    assert coverage > 0.95


def test_temporal_inpaint_beats_spatial_on_panning_scene():
    # Pan of 6 px/frame with +-2 neighbours reveals up to 12 px: enough to see
    # behind a ~16 px wide logo, which spatial inpainting can only guess at.
    n, h, w = 9, 80, 120
    clean = translating_texture(n, h, w, dx=6.0)
    alpha = sparkle_alpha(h, w, 60, 40, 8, 0.9)
    a = alpha[None, ..., None]
    observed = np.clip((1 - a) * clean + a * 255 + 0.5, 0, 255).astype(np.uint8)
    mask = ((alpha > 0) * 255).astype(np.uint8)
    mask = np.maximum(mask, np.roll(mask, 1, 0))  # slight dilation

    t = n // 2
    spatial = inpaint_fast(observed[t], mask)
    temporal = TemporalInpainter(mask, radius=2, smoothing=0).process(list(observed[t - 2 : t + 3]), 2)
    region = mask > 0
    p_t, p_s = psnr(temporal, clean[t], region), psnr(spatial, clean[t], region)
    print(f"panning scene PSNR: spatial {p_s:.1f} dB, temporal {p_t:.1f} dB")
    assert p_t > p_s + 3


def test_iter_windows():
    frames = list(range(6))
    out = [(win, c) for win, c in iter_windows(frames, 2)]
    assert [win[c] for win, c in out] == frames
    assert out[0] == ([0, 1, 2], 0)
    assert out[3] == ([1, 2, 3, 4, 5], 2)
    assert out[5] == ([3, 4, 5], 2)
    assert [w[c] for w, c in iter_windows(frames, 0)] == frames


def test_crop_plan_excludes_logo_and_keeps_aspect():
    box = Box(1700, 950, 180, 100)
    plan = plan_crop(1920, 1080, box)
    c = plan.crop
    overlaps = not (c.x + c.w <= box.x or box.x + box.w <= c.x or c.y + c.h <= box.y or box.y + box.h <= c.y)
    assert not overlaps
    assert abs(c.w / c.h - 1920 / 1080) < 0.01
    assert (plan.out_w, plan.out_h) == (1920, 1080)
