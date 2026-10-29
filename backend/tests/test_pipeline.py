"""prepare(): the per-box cache is shared by every mode (no ffmpeg needed)."""

from app.video import pipeline
from app.video.detection import Box
from app.video.ffmpeg_io import VideoInfo
from tests.synthetic import make_video


def test_modes_share_one_sampling_pass(tmp_path, monkeypatch):
    v = make_video()
    info = VideoInfo(320, 180, "24/1", 24.0, "yuv420p", 2.0, 48, False, None, "mp4", {})
    calls = []

    def fake_sample_rois(path, info, roi, n=32):
        calls.append(roi)
        return v.observed[:, roi.slices[0], roi.slices[1]].copy()

    monkeypatch.setattr(pipeline, "sample_rois", fake_sample_rois)
    box = Box(*v.logo_box).pad(4, 320, 180)

    for mode in ("inpaint_fast", "alpha", "inpaint_temporal", "alpha"):
        proc = pipeline.prepare("unused.mp4", info, pipeline.RenderParams(mode, box), cache_dir=tmp_path)
        assert proc.process([v.observed[0]], 0).shape == v.observed[0].shape

    assert len(calls) == 1  # one decode of the samples for this box, across all modes
    # A different box needs its own samples.
    pipeline.prepare("unused.mp4", info, pipeline.RenderParams("alpha", box.pad(2, 320, 180)), cache_dir=tmp_path)
    assert len(calls) == 2
