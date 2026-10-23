"""Load an FL Studio project (.flp) into a Song using pyflp."""
import pyflp

from unbolt.daw import Song, Track

_NAMES = {n: i for i, n in enumerate(("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"))}


def _midi(key):
    name = key.rstrip("0123456789")
    return int(key[len(name):]) * 12 + _NAMES[name]


def load_flp(path):
    project = pyflp.parse(path)
    ppq = project.ppq
    song = Song(float(project.tempo), [])
    channels = {c.iid: c for c in project.channels}
    tracks = {}

    def track_for(iid):
        if iid not in tracks:
            ch = channels.get(iid)
            tracks[iid] = Track(getattr(ch, "name", None) or getattr(ch, "internal_name", None) or f"Channel {iid}")
            song.tracks.append(tracks[iid])
        return tracks[iid]

    def add_pattern(pattern, offset, limit):
        for n in pattern.notes:
            start = n.position / ppq
            if limit is not None and start >= limit:
                continue
            ch = channels.get(n.rack_channel)
            sample = getattr(ch, "sample_path", None)
            sample = str(sample) if sample else None
            track_for(n.rack_channel).notes.append((offset + start, n.length / ppq, _midi(n.key), (n.velocity or 100) / 127, sample))

    placed = False
    for arr in project.arrangements:
        for tr in arr.tracks:
            for item in tr:
                if getattr(item, "muted", False):
                    continue
                pattern = getattr(item, "pattern", None)
                if pattern is not None:
                    add_pattern(pattern, item.position / ppq, item.length / ppq)
                    placed = True
                elif getattr(item, "channel", None) is not None:
                    sample = getattr(item.channel, "sample_path", None)
                    if sample:
                        track_for(item.channel.iid).clips.append((item.position / ppq, item.length / ppq, str(sample)))
                        placed = True
    if not placed:   # nothing on the playlist: play the patterns one after another
        offset = 0.0
        for pattern in project.patterns:
            add_pattern(pattern, offset, None)
            offset += max((pattern.length or 0) / ppq, 4.0)
        song.warnings.append("Playlist is empty; patterns were played in order.")
    song.warnings.append("FL Studio plugins, mixer effects and automation are not reproduced; instruments play through a basic synth.")
    return song
