from pathlib import Path

main = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = main.read_text()

# v0.4.5 introduced a new graph gesture layer that conflicts with point dragging
# on some iPhone layouts. Keep all v0.4.5 UI/timeline features, but return the
# full curve editor to the proven v0.4.4 interaction engine.
s = s.replace('CurveEditorGraphV45(model:model,target:target,selectedPointID:$selectedPoint)',
              'CurveEditorGraphV4(model:model,target:target,selectedPointID:$selectedPoint)')
main.write_text(s)

enh = Path('VeloCutAI/VeloCutAI/VeloCutV4Enhancements.swift')
e = enh.read_text()

# Keep generous invisible touch targets while making the visible points/handles
# compact. This preserves easy finger dragging without covering the graph.
e = e.replace('Circle().fill(Color.clear).frame(width: 48, height: 48)',
              'Circle().fill(Color.clear).frame(width: 44, height: 44)')
e = e.replace('.frame(width: selected ? 22 : 17, height: selected ? 22 : 17)',
              '.frame(width: selected ? 14 : 11, height: selected ? 14 : 11)')
e = e.replace('Circle().fill(Color.clear).frame(width: 36, height: 36)',
              'Circle().fill(Color.clear).frame(width: 32, height: 32)')
e = e.replace('Circle().fill(Color.orange).frame(width: 10, height: 10)',
              'Circle().fill(Color.orange).frame(width: 8, height: 8)')
enh.write_text(e)

print('Restored stable v0.4.4 curve interaction engine with compact v0.4.6 controls')
