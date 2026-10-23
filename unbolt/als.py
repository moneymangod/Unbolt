"""Load an Ableton Live set (.als, gzipped XML) into a Song."""
import gzip
import math
import os
import xml.etree.ElementTree as ET

from unbolt.daw import Song, Track


def _val(el, path, default=None):
    node = el.find(path)
    return node.get("Value", default) if node is not None else default


def _name(track):
    return _val(track, "Name/EffectiveName") or _val(track, "Name/UserName") or track.tag


def _sample_path(clip, base):
    ref = clip.find("SampleRef/FileRef")
    if ref is None:
        return None
    full = _val(ref, "Path")
    if full and os.path.exists(full):
        return full
    parts = [e.get("Dir") for e in ref.findall("RelativePath/RelativePathElement")]
    rel = os.path.join(base, *[p for p in parts if p], _val(ref, "Name", ""))
    return rel if os.path.exists(rel) else full or rel


def _midi_clip(clip, track):
    start, end = float(_val(clip, "CurrentStart", 0)), float(_val(clip, "CurrentEnd", 0))
    loop = clip.find("Loop")
    loop_start, loop_end = float(_val(loop, "LoopStart", 0)), float(_val(loop, "LoopEnd", end - start))
    first = loop_start + float(_val(loop, "StartRelative", 0))
    looped = _val(loop, "LoopOn", "false") == "true"
    span = max(loop_end - loop_start, 1e-6)
    for kt in clip.iterfind("Notes/KeyTracks/KeyTrack"):
        key = int(_val(kt, "MidiKey", 60))
        for ev in kt.iterfind("Notes/MidiNoteEvent"):
            if ev.get("IsEnabled", "true") == "false":
                continue
            t, dur, vel = float(ev.get("Time")), float(ev.get("Duration")), float(ev.get("Velocity", 100)) / 127
            pos = t - first
            if pos < 0:
                if not looped:
                    continue
                pos += span
            elif not looped and t >= loop_end:
                continue
            for k in range(math.ceil((end - start) / span) + 1 if looped else 1):
                at = start + pos + k * span
                if at < end:
                    track.notes.append((at, min(dur, end - at), key, vel, None))


def load_als(path):
    with gzip.open(path, "rb") as f:
        root = ET.fromstring(f.read())
    base = os.path.dirname(os.path.abspath(path))
    tempo = float(_val(root, "LiveSet/MasterTrack/DeviceChain/Mixer/Tempo/Manual", 120))
    song = Song(tempo, [])
    for el in root.find("LiveSet/Tracks"):
        if el.tag not in ("MidiTrack", "AudioTrack"):
            continue
        track = Track(_name(el))
        clips = el.findall(".//ArrangerAutomation/Events/*")
        if not clips:   # session-only project: lay out each track's first clip from time 0
            clips = [c for c in el.findall(".//ClipSlotList//Value/*") if c.tag in ("MidiClip", "AudioClip")][:1]
            song.warnings.append("No arrangement clips found; used session clips instead.")
        for clip in clips:
            if clip.tag == "MidiClip":
                _midi_clip(clip, track)
            elif clip.tag == "AudioClip":
                s, e = float(_val(clip, "CurrentStart", 0)), float(_val(clip, "CurrentEnd", 0))
                p = _sample_path(clip, base)
                if p:
                    track.clips.append((s, e - s, p))
        song.tracks.append(track)
    song.warnings.append("Ableton instruments, effects, warping and automation are not reproduced; MIDI plays through a basic synth.")
    return song
