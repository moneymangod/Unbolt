"""Load an Audacity project (.aup3, a SQLite database) as audio by stitching its stored sample blocks."""
import sqlite3

import numpy as np

_FLOAT, _INT16, _INT24 = 0x0004000F, 0x00020001, 0x00040001


def load_aup3(path):
    """Return (stereo float32 array, warnings)."""
    db = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT sampleformat, samples FROM sampleblocks ORDER BY blockid").fetchall()
    finally:
        db.close()
    parts = []
    for fmt, blob in rows:
        if fmt == _FLOAT:
            parts.append(np.frombuffer(blob, "<f4"))
        elif fmt == _INT16:
            parts.append(np.frombuffer(blob, "<i2").astype(np.float32) / 32768)
        elif fmt == _INT24:
            b = np.frombuffer(blob[:len(blob) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
            parts.append(np.where(v >= 0x800000, v - 0x1000000, v) / 8388608.0)
    if not parts:
        raise ValueError("No audio blocks found in this Audacity project")
    mono = np.concatenate(parts).astype(np.float32)
    return np.repeat(mono[:, None], 2, 1), [
        "Sample rate is assumed to be 44100 Hz and tracks play one after another; Audacity's track layout isn't decoded."]
