from pathlib import Path
p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()
if '@State private var multiSelectMode' not in s:
    candidates = [
        '@State private var laneHeights:[Int:CGFloat] = [0:46,1:46,2:46]',
        '@State private var laneHeights:[Int:CGFloat]=[0:46,1:46,2:46]'
    ]
    for old in candidates:
        if old in s:
            s = s.replace(old, old + '\n    @State private var multiSelectMode = false\n    @State private var multiSelectedClips:Set<UUID> = []', 1)
            break
    else:
        raise RuntimeError('laneHeights state not found for v0.4.5 compile fix')
p.write_text(s)
print('Applied v0.4.5 multi-select state compile fix')
