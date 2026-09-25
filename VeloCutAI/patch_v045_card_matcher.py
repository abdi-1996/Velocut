from pathlib import Path
p = Path('VeloCutAI/patch_v045_pro_ui.py')
s = p.read_text()
old = """if old_card not in s:\n    raise RuntimeError('Resizable clip card not found')\ns = s.replace(old_card, new_card, 1)"""
new = """card_pattern = re.compile(r'ResizableTimelineClipCardV4\\(\\s*clip:l\\.clip,.*?onMove:\\{model\\.moveClip\\(l\\.id,translation:\\$0,pps:pps\\)\\}\\s*\\)', re.S)\ns, count = card_pattern.subn(new_card, s, count=1)\nif count != 1:\n    raise RuntimeError('Resizable clip card not found')"""
if old not in s:
    raise RuntimeError('Clip card matcher block not found inside v0.4.5 patch script')
s = s.replace(old, new, 1)
p.write_text(s)
print('Relaxed v0.4.5 clip card matcher')
