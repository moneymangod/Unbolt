# Unbolt

**Unbolt locked file formats.** Drop a Figma, Ableton, FL Studio or Audacity project onto a tiny window (or use the command line) and get a normal PNG, PDF, PPTX, MP3, MP4 or WAV out of it. No account, no cloud, nothing leaves your computer.

<p align="center"><img src="assets/icon.png" width="96" alt="Unbolt icon"></p>

## ⭐ Before you download: please star this repo

Unbolt is free and open source, and stars are how other people find it. **Please click the ★ Star button at the top of this page first, then download.** It takes one second and it genuinely helps.

(GitHub can't make you do it, so this is on the honor system. Thank you!)

## Download

1. Star the repo (see above).
2. Open the [latest release](https://github.com/moneymangod/Unbolt/releases/latest) and download:
   - **`Unbolt.exe`**: the small drag-and-drop window.
   - **`unbolt-cli.exe`**: the command-line version.
3. Run it. There is nothing to install. Windows may show a SmartScreen warning because the app isn't code-signed; choose *More info* then *Run anyway*.

## Use it

### The window

Drop files onto it (or click it to browse), pick an output format, press **Convert**. Results are saved next to each file unless you choose another folder. Existing files are never overwritten; a copy gets a number, like `song (2).mp3`.

Press **Add right-click menu** to get *Convert with Unbolt* when you right-click a supported file in Explorer, like 7-Zip. **Remove it** takes it away again. It only changes your own Windows user, not the whole machine.

### The command line

```
unbolt-cli --list
unbolt-cli song.als --to mp3
unbolt-cli design.fig mockup.fig --to pdf -o C:\exports
```

It prints the path of every file it writes, prints notes about limits to stderr, and exits with code 1 if any file failed.

## What it converts

| Input | Output | What you get |
|---|---|---|
| `.fig` (Figma) | PNG, PDF, PPTX | Every top-level frame drawn as an image. PNG is one file per frame, PDF has one page per frame, PPTX one slide per frame. |
| `.als` (Ableton Live) | MP3, WAV, MP4 | The arrangement's MIDI notes and audio clips mixed down. MP4 adds a note-view video with a moving playhead. |
| `.flp` (FL Studio) | MP3, WAV, MP4 | Patterns and playlist clips mixed down, same as above. |
| `.aup3` (Audacity) | WAV, MP3 | The audio samples stored in the project. |

### Be aware of the limits

Unbolt reads these formats without the original apps, so some things can't be reproduced exactly:

- **Music projects are a rough mixdown, not a bounce from the DAW.** Synths, plugins, effects, automation and warping live inside Ableton and FL Studio and aren't reproduced. MIDI notes play through a plain built-in synth. Audio clips are only included if their sample files still exist on your disk.
- **Figma frames are drawn by Unbolt, not by Figma.** Shapes, vector paths, solid and gradient fills, strokes, images and basic text are drawn. Drop shadows, blurs, blend modes, component overrides and fonts you don't have installed will differ. The PPTX holds one picture per slide, not editable shapes.
- **Audacity** projects assume 44.1 kHz and play tracks one after another.

Unbolt prints a note when any of these apply to the file you converted.

> **Status:** the converters were developed against sample files built from each format's structure. Files saved by the real apps can contain things the samples don't. If one fails or looks wrong, please [open an issue](https://github.com/moneymangod/Unbolt/issues) (attach the file if you can share it).

## How it works

- **Figma `.fig`**: a `.fig` is a ZIP (or a raw blob) holding `canvas.fig`, which starts with a `fig-kiwi` header followed by compressed chunks (deflate or zstd). The first chunk is a binary [Kiwi](https://github.com/evanw/kiwi) schema describing the file; the second is the whole document encoded with that schema. Unbolt decodes the schema, decodes the document into a tree of layers, then draws each top-level frame with Pillow: rectangles, ellipses, vector paths (flattened Béziers), text, gradients and images, with clipping for frames. Frames then become PNG, PDF or PPTX.
- **Ableton `.als`**: a gzip-compressed XML file. Unbolt reads the tempo, the tracks, the arrangement's MIDI clips (including loops) and audio clips.
- **FL Studio `.flp`**: parsed with [PyFLP](https://github.com/demberto/PyFLP) into patterns, notes and the playlist.
- **Rendering music**: both DAW formats become the same simple song model. Notes are synthesized with a basic additive tone, audio clips are decoded with ffmpeg and placed on the timeline, and the mix is written out as WAV/MP3. MP4 draws a note view and muxes in the audio.
- **Audacity `.aup3`**: a SQLite database. The stored sample blocks are read in order and written out as audio.

## Build from source

Needs Windows and Python 3.12.

```powershell
git clone https://github.com/moneymangod/Unbolt
cd Unbolt
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python tests\smoke.py     # converts generated sample files to every output
.\build.ps1                               # builds dist\Unbolt.exe and dist\unbolt-cli.exe
```

Adding a format is one loader function plus one line in `FORMATS` in `unbolt/convert.py`.

## License

[GPL-3.0](LICENSE). Unbolt uses PyFLP (GPL-3.0) and ships an ffmpeg build through `imageio-ffmpeg`, so the whole program is released under the GPL. Kiwi decoding was written with reference to the MIT-licensed [kiwi](https://github.com/evanw/kiwi) project.
