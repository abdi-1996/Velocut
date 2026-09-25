from pathlib import Path

p = Path('VeloCutAI/VeloCutAI/SpeedCurves.swift')
s = p.read_text()
s = s.replace(
    'mutating func setPointMode(_ id: UUID, mode: CurveInterpolation, resetHandles: Bool = false) {',
    'mutating func setPointMode(_ id: UUID, mode: CurveInterpolation, resetHandles shouldResetHandles: Bool = false) {'
)
s = s.replace(
    'if resetHandles || mode == .smooth { resetHandles(pointID: id) }',
    'if shouldResetHandles || mode == .smooth { resetHandles(pointID: id) }'
)
p.write_text(s)
print('Applied v0.4.4 compile hotfixes')
