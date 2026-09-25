from pathlib import Path

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# Swift 5 parser requires consistent whitespace around '=' in these generated cards.
s=s.replace('@State private var drag:CGSize=.zero','@State private var drag:CGSize = .zero')
s=s.replace('drag=.zero','drag = .zero')

p.write_text(s)
print('Applied v0.6.1 fresh UI compile spacing fixes')
