from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# v0.4.7 adds a floating capsule in the lower-right corner of Preview.
# v0.5.x already has the dedicated playback row directly below Preview,
# so remove only the floating duplicate while keeping the top-right menu.
pattern = re.compile(r'''\n\s*HStack\{\n\s*Spacer\(\)\n\s*HStack\(spacing:6\)\{\n\s*Button\{\n\s*model\.projectLoopEnabled\.toggle\(\).*?\n\s*\.padding\(\.bottom,8\)''', re.S)

s, count = pattern.subn('', s, count=1)
if count != 1:
    raise RuntimeError('Floating Preview playback capsule not found')

p.write_text(s)
print('Removed floating Preview playback controls; playback row below Preview remains')
