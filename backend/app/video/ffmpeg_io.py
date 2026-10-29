"""FFmpeg/ffprobe wrappers. Frames move through stdin/stdout pipes as raw BGR24.

No intermediate image files are ever written.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Pixel formats libx264 can encode. Anything else falls back to yuv420p.
X264_PIX_FMTS = {
    "yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p",
    "yuv420p10le", "yuv422p10le", "yuv444p10le", "nv12",
}
# Audio codecs we can stream-copy into an MP4/MOV container.
MP4_AUDIO_COPY = {"aac", "mp3", "alac", "ac3", "eac3", "opus", "flac"}


class FFmpegError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: str  # exact rational, e.g. "24/1" or "30000/1001"
    fps_float: float
    pix_fmt: str
    duration: float
    nb_frames: int
    has_audio: bool
    audio_codec: str | None
    format_name: str
    color: dict = field(default_factory=dict)  # color_range / primaries / trc / space

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VideoInfo":
        return cls(**d)


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip()[-2000:])
    return proc.stdout


def probe(path: str | Path) -> VideoInfo:
    out = _run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    data = json.loads(out)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError("No video stream found")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width, height = int(video["width"]), int(video["height"])
    # ffmpeg auto-rotates on decode, so report display dimensions.
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    if abs(rotation) % 180 == 90:
        width, height = height, width

    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    if rate in ("0/0", "0/1"):
        rate = video.get("r_frame_rate", "30/1")
    fps = Fraction(rate)
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0.0)
    nb = int(video.get("nb_frames") or 0) or max(1, round(duration * float(fps)))

    color = {k: video[k] for k in ("color_range", "color_primaries", "color_transfer", "color_space")
             if video.get(k) and video[k] != "unknown"}
    return VideoInfo(
        width=width,
        height=height,
        fps=f"{fps.numerator}/{fps.denominator}",
        fps_float=float(fps),
        pix_fmt=video.get("pix_fmt", "yuv420p"),
        duration=duration,
        nb_frames=nb,
        has_audio=audio is not None,
        audio_codec=audio.get("codec_name") if audio else None,
        format_name=data.get("format", {}).get("format_name", ""),
        color=color,
    )


class FrameReader:
    """Iterate decoded frames as (H, W, 3) uint8 BGR arrays.

    ``vf`` is an optional ffmpeg filter chain; pass ``out_size`` when the chain
    changes the frame size (e.g. ``crop`` / ``scale`` / ``fps``).
    """

    def __init__(self, path: str | Path, info: VideoInfo, start: float | None = None,
                 duration: float | None = None, vf: str | None = None, out_size: tuple[int, int] | None = None):
        self.path, self.info = str(path), info
        self.start, self.duration, self.vf = start, duration, vf
        self.w, self.h = out_size or (info.width, info.height)

    def __iter__(self) -> Iterator[np.ndarray]:
        cmd = [FFMPEG, "-v", "error", "-nostdin"]
        if self.start:
            cmd += ["-ss", f"{self.start:.3f}"]
        cmd += ["-i", self.path]
        if self.duration:
            cmd += ["-t", f"{self.duration:.3f}"]
        if self.vf:
            cmd += ["-vf", self.vf]
        cmd += ["-an", "-sn", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]

        frame_bytes = self.w * self.h * 3
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, bufsize=frame_bytes)
            finished = False
            try:
                while True:
                    buf = proc.stdout.read(frame_bytes)
                    if len(buf) < frame_bytes:
                        finished = True
                        if buf:
                            # Leftover bytes mean the output size isn't what we
                            # asked for; reshaping would silently skew frames.
                            raise FFmpegError(f"partial frame ({len(buf)} of {frame_bytes} bytes): size mismatch")
                        break
                    yield np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
            finally:
                # If the consumer stopped early we kill ffmpeg on purpose.
                proc.stdout.close()
                if not finished and proc.poll() is None:
                    proc.kill()
                proc.wait()
            if finished and proc.returncode != 0:
                raise FFmpegError(_tail(err) or f"ffmpeg exited with {proc.returncode}")


def _tail(f) -> str:
    f.seek(0)
    return f.read().decode(errors="replace").strip()[-2000:]


def output_container(src: str | Path) -> str:
    """MOV stays MOV; MP4 and WebM become MP4 (H.264 isn't valid in WebM)."""
    return ".mov" if Path(src).suffix.lower() == ".mov" else ".mp4"


class FrameWriter:
    """Encode BGR frames to H.264 while copying audio + metadata from the source."""

    def __init__(self, out_path: str | Path, src_path: str | Path, info: VideoInfo, high_quality: bool = False,
                 start: float | None = None, duration: float | None = None, preset: str | None = None):
        pix_fmt = info.pix_fmt if info.pix_fmt in X264_PIX_FMTS else "yuv420p"
        if pix_fmt == "nv12":
            pix_fmt = "yuv420p"

        cmd = [FFMPEG, "-v", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{info.width}x{info.height}", "-r", info.fps, "-i", "-"]
        # Second input: the original file, for audio and metadata.
        if start:
            cmd += ["-ss", f"{start:.3f}"]
        if duration:
            cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-i", str(src_path)]

        cmd += ["-map", "0:v:0", "-map", "1:a?", "-map_metadata", "1"]
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", preset or ("slow" if high_quality else "veryfast"),
                "-pix_fmt", pix_fmt, "-r", info.fps]
        for key, flag in (("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc"),
                          ("color_space", "-colorspace"), ("color_range", "-color_range")):
            if key in info.color:
                cmd += [flag, info.color[key]]
        if info.has_audio:
            if info.audio_codec in MP4_AUDIO_COPY:
                cmd += ["-c:a", "copy"]
            else:
                # e.g. Vorbis from WebM can't live in MP4; re-encode only then.
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        cmd += ["-movflags", "+faststart+use_metadata_tags", "-shortest", str(out_path)]

        self._err = tempfile.TemporaryFile()
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._err)

    def write(self, frame: np.ndarray) -> None:
        try:
            self._proc.stdin.write(np.ascontiguousarray(frame, np.uint8).tobytes())
        except BrokenPipeError as e:
            self._proc.wait()
            raise FFmpegError(_tail(self._err) or "ffmpeg encoder exited early") from e

    def close(self) -> None:
        if self._proc.stdin and not self._proc.stdin.closed:
            self._proc.stdin.close()
        rc = self._proc.wait()
        msg = _tail(self._err)
        self._err.close()
        if rc != 0:
            raise FFmpegError(msg or f"ffmpeg exited with {rc}")

    def abort(self) -> None:
        self._proc.kill()
        self._proc.wait()
        self._err.close()

    def __enter__(self) -> "FrameWriter":
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.close()
        else:
            self.abort()
