"""Generate small synthetic test files (no real .flp/.fig can be fabricated reliably, so only .als here)."""
import gzip
import sys

notes = "".join(
    f'<KeyTrack><Notes><MidiNoteEvent Time="{t}" Duration="0.5" Velocity="100" IsEnabled="true"/></Notes><MidiKey Value="{k}"/></KeyTrack>'
    for t, k in [(0, 60), (1, 64), (2, 67), (3, 72)]
)
xml = f"""<?xml version="1.0"?><Ableton><LiveSet>
<MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="120"/></Tempo></Mixer></DeviceChain></MasterTrack>
<Tracks><MidiTrack><Name><EffectiveName Value="Lead"/></Name><DeviceChain><MainSequencer><ClipTimeable><ArrangerAutomation><Events>
<MidiClip Time="0"><CurrentStart Value="0"/><CurrentEnd Value="8"/>
<Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="0"/><LoopOn Value="true"/></Loop>
<Notes><KeyTracks>{notes}</KeyTracks></Notes></MidiClip>
</Events></ArrangerAutomation></ClipTimeable></MainSequencer></DeviceChain></MidiTrack></Tracks></LiveSet></Ableton>"""
with gzip.open(sys.argv[1], "wb") as f:
    f.write(xml.encode())
