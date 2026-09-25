from pathlib import Path

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()
s = s.replace('in:.05...20', 'in:0.05...20')
p.write_text(s)
print('Applied v0.4.7 Swift compile fixes')
