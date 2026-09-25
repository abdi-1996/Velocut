from pathlib import Path
p = Path('VeloCutAI/patch_v045_pro_ui.py')
s = p.read_text()
s = s.replace(
    "r'    private var topBar:some View\\{.*?\\n\\n    private var preview:'",
    "r'    private var topBar:some View\\s*\\{.*?    private var preview:'"
)
s = s.replace(
    "r'    private var playback:some View\\{.*?\\n\\n    private var timeline:'",
    "r'    private var playback:some View\\s*\\{.*?    private var timeline:'"
)
p.write_text(s)
print('Relaxed v0.4.5 compact Swift matchers')
