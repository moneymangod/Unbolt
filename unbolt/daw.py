"""Shared song model, a simple synth/sample mixer, and WAV/MP3/MP4 export for DAW projects."""
import colorsys
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

SR = 44100
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Track:
    name: str
    notes: list = field(default_factory=list)   # (start_beat, dur_beats, midi_key, velocity 0-1, sample_path or None)
    clips: list = field(default_factory=list)   # (start_beat, dur_beats, sample_path)


@dataclass
class Song:
    tempo: float
    tracks: list
    warnings: list = field(default_factory=list)

    @property
    def beats(self):
        ends = [n[0] + n[1] for t in self.tracks for n in t.notes] + [c[0] + c[1] for t in self.tracks for c in t.clips]
        return max(ends, default=0)


def _decode(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                       capture_output=True, creationflags=_NO_WINDOW)
    if p.returncode or not p.stdout:
        raise OSError(p.stderr.decode(errors="replace")[:200])
    return np.frombuffer(p.stdout, np.int16).reshape(-1, 2).astype(np.float32) / 32768


def _tone(key, secs, vel):
    n = max(int(secs * SR), 1)
    t = np.arange(n) / SR
    f = 440 * 2 ** ((key - 69) / 12)
    wave_ = np.sin(2 * np.pi * f * t) + .3 * np.sin(4 * np.pi * f * t) + .12 * np.sin(6 * np.pi * f * t)
    env = np.minimum(t / .005, 1) * np.exp(-t * 2.5 / max(secs, .1)) * np.minimum((secs - t) / .03, 1).clip(0, 1)
    return (wave_ * env * vel * .18).astype(np.float32)


def render_audio(song):
    spb = 60 / song.tempo
    out = np.zeros((int((song.beats * spb + 2) * SR), 2), np.float32)
    cache = {}

    def sample(path):
        if path not in cache:
            try:
                cache[path] = _decode(path)
            except OSError:
                cache[path] = None
                song.warnings.append(f"Sample not found or unreadable, skipped: {path}")
        return cache[path]

    def put(data, at):
        i = int(at * spb * SR)
        n = min(len(data), len(out) - i)
        if n > 0:
            out[i:i + n] += data[:n] if data.ndim == 2 else data[:n, None]

    for tr in song.tracks:
        for start, dur, path in tr.clips:
            s = sample(path)
            if s is not None:
                put(s[:int(dur * spb * SR)], start)
        for start, dur, key, vel, path in tr.notes:
            if path:
                s = sample(path)
                if s is not None:
                    put(s * vel, start)
            else:
                put(_tone(key, dur * spb, vel), start)
    peak = np.abs(out).max()
    return out / peak * .9 if peak > .9 else out


def write_wav(audio, path):
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


def _ffmpeg(args):
    p = subprocess.run([FFMPEG, "-y", "-v", "error", *args], capture_output=True, creationflags=_NO_WINDOW)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace")[:300])


def piano_roll(song, size=(960, 540)):
    w, h = size
    img = Image.new("RGB", size, (24, 24, 30))
    d = ImageDraw.Draw(img)
    tracks = [t for t in song.tracks if t.notes or t.clips]
    if not tracks:
        return img
    total, row = max(song.beats, 1), h / len(tracks)
    for i, t in enumerate(tracks):
        r, g, b = colorsys.hsv_to_rgb(i * .13 % 1, .6, .95)
        col = (int(r * 255), int(g * 255), int(b * 255))
        y0 = i * row
        d.line([(0, y0), (w, y0)], fill=(50, 50, 60))
        keys = [n[2] for n in t.notes]
        lo, hi = (min(keys), max(keys) + 1) if keys else (0, 1)
        for s, dur, _ in t.clips:
            d.rectangle([s / total * w, y0 + 3, (s + dur) / total * w, y0 + row - 3], fill=tuple(c // 3 for c in col))
        for s, dur, key, vel, _ in t.notes:
            y = y0 + row - 4 - (key - lo) / max(hi - lo, 1) * (row - 8)
            d.rectangle([s / total * w, y - 2, max((s + dur) / total * w, s / total * w + 2), y], fill=col)
        d.text((4, y0 + 2), t.name[:24], fill=(235, 235, 235))
    return img


def write_audio(audio, path, fmt):
    """Write a float32 stereo array as WAV or MP3."""
    if fmt == "wav":
        write_wav(audio, path)
        return
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "mix.wav")
        write_wav(audio, wav)
        _ffmpeg(["-i", wav, "-codec:a", "libmp3lame", "-q:a", "2", path])


def export(song, path, fmt):
    audio = render_audio(song)
    if fmt != "mp4":
        write_audio(audio, path, fmt)
        return
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "mix.wav")
        write_wav(audio, wav)
        base = np.asarray(piano_roll(song))
        h, w, _ = base.shape
        fps, frames = 15, max(int(len(audio) / SR * 15), 1)
        total = max(song.beats * 60 / song.tempo, 1e-3)
        p = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                              "-r", str(fps), "-i", "-", "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                              "-c:a", "aac", "-shortest", path],
                             stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
        try:
            for f in range(frames):
                frame = base.copy()
                x = min(int(f / fps / total * w), w - 2)
                frame[:, x:x + 2] = (255, 255, 255)
                p.stdin.write(frame.tobytes())
            p.stdin.close()
        except BrokenPipeError:
            pass
        err = p.stderr.read().decode(errors="replace")
        if p.wait():
            raise RuntimeError(err[:300])
