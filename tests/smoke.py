"""Smoke test: generate small synthetic .als/.fig/.aup3 files and convert each to every output format.

Run from the repo root:  python tests/smoke.py
The samples are built from the formats' documented structure, so this checks the code runs end to end;
it does not replace testing with files saved by the real applications.
"""
import os
import shutil
import sqlite3
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from unbolt.convert import FORMATS, convert  # noqa: E402

src, out = os.path.join(ROOT, "tests", "samples"), os.path.join(ROOT, "tests", "out")
shutil.rmtree(out, ignore_errors=True)   # conversions never overwrite, so start from an empty folder
os.makedirs(src, exist_ok=True)
for script, name in (("make_samples.py", "demo.als"), ("make_fig.py", "demo.fig")):
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", script), os.path.join(src, name)], check=True)

aup3 = os.path.join(src, "demo.aup3")
if os.path.exists(aup3):
    os.remove(aup3)
db = sqlite3.connect(aup3)
db.execute("CREATE TABLE sampleblocks (blockid INTEGER PRIMARY KEY, sampleformat INTEGER, samples BLOB)")
tone = (np.sin(2 * np.pi * 440 * np.arange(44100) / 44100) * .5).astype("<f4")
db.execute("INSERT INTO sampleblocks VALUES (1, ?, ?)", (0x0004000F, tone.tobytes()))
db.commit()
db.close()

failures = 0
for name in sorted(os.listdir(src)):
    ext = os.path.splitext(name)[1]
    if ext not in FORMATS:
        continue
    for fmt in FORMATS[ext][0]:
        try:
            files, _ = convert(os.path.join(src, name), fmt, out)
            assert files and all(os.path.getsize(f) > 0 for f in files), "empty output"
            print(f"ok    {name} -> {fmt}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {name} -> {fmt}: {type(e).__name__}: {e}")
print("all passed" if not failures else f"{failures} failed")
sys.exit(1 if failures else 0)
