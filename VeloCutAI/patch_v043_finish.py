from pathlib import Path

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

replacements = {
    'onChange:{model.setTrimStartInteractive(l.id,$0)}': 'onChange:{model.setTrimStartInteractive(l.id,$0)},onEnd:{model.finishInteractiveEdit()}',
    'onChange:{model.setTrimEndInteractive(l.id,$0)}': 'onChange:{model.setTrimEndInteractive(l.id,$0)},onEnd:{model.finishInteractiveEdit()}',
    'onChange:{newStart,newDuration in model.setSpeedFXStartInteractive(fx.id,start:newStart,duration:newDuration)}': 'onChange:{newStart,newDuration in model.setSpeedFXStartInteractive(fx.id,start:newStart,duration:newDuration)},onEnd:{model.finishInteractiveEdit()}',
    'onChange:{_,newDuration in model.setSpeedFXDurationInteractive(fx.id,newDuration)}': 'onChange:{_,newDuration in model.setSpeedFXDurationInteractive(fx.id,newDuration)},onEnd:{model.finishInteractiveEdit()}',
}

for old, new in replacements.items():
    if old not in s:
        raise RuntimeError(f'Expected v0.4.2 interaction not found: {old}')
    s = s.replace(old, new, 1)

p.write_text(s)
print('Added stable interaction finish handlers for v0.4.3')
