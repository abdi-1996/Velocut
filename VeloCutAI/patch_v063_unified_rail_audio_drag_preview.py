from pathlib import Path
import re

main=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=main.read_text()

# VeloCut v0.5.9
# A) Keep a live per-audio drag preview so the clip visibly follows the finger.
state_pat=re.compile(r'(@State\s+private\s+var\s+timelineDragStart\s*:[^\n]+)')
m=state_pat.search(s)
if not m:
    raise RuntimeError('timelineDragStart state missing')
if 'audioDragPreview' not in s:
    s=s[:m.end()]+'''\n    @State private var audioDragPreview: [UUID: CGSize] = [:]'''+s[m.end():]

# Replace v0.5.8 audio gesture with a live offset preview.
audio_pat=re.compile(r'''(\.overlay\(\n\s*RoundedRectangle\(cornerRadius:6\).*?\.position\(x:x,y:top\+laneH/2\)\n\s*\.onTapGesture\{model\.selectAudioClip\(a\.id\)\})\n\s*\.simultaneousGesture\(\n\s*LongPressGesture\(minimumDuration:0\.30\)\n\s*\.sequenced\(before:DragGesture\(minimumDistance:0\)\)\n\s*\.onChanged\{value in\n\s*if case \.second\(true,_\)=value \{ model\.beginTimelineItemMove\(\) \}\n\s*\}\n\s*\.onEnded\{value in\n\s*defer\{model\.endTimelineItemMove\(\)\}\n\s*if case \.second\(true,let drag\?\)=value \{\n\s*let snapped=snappedAudioTranslation\(a,drag\.translation,pps:pps\)\n\s*if hypot\(snapped\.width,snapped\.height\)>=6 \{ model\.moveAudioClip\(a\.id,translation:snapped,pps:pps\) \}\n\s*\}\n\s*\}\n\s*\)''',re.S)

def repl(m):
    return m.group(1)+'''\n                    .offset(audioDragPreview[a.id] ?? .zero)\n                    .zIndex(audioDragPreview[a.id] == nil ? 20 : 80)\n                    .simultaneousGesture(\n                        LongPressGesture(minimumDuration:0.30)\n                            .sequenced(before:DragGesture(minimumDistance:0))\n                            .onChanged{value in\n                                if case .second(true,let drag?)=value {\n                                    model.beginTimelineItemMove()\n                                    let snapped=snappedAudioTranslation(a,drag.translation,pps:pps)\n                                    audioDragPreview[a.id]=snapped\n                                }\n                            }\n                            .onEnded{value in\n                                let preview=audioDragPreview[a.id] ?? .zero\n                                audioDragPreview[a.id]=nil\n                                defer{model.endTimelineItemMove()}\n                                if case .second(true,_)=value {\n                                    if hypot(preview.width,preview.height)>=6 { model.moveAudioClip(a.id,translation:preview,pps:pps) }\n                                }\n                            }\n                    )'''
s,n=audio_pat.subn(repl,s,count=1)
if n!=1:
    raise RuntimeError('v0.5.8 audio drag gesture block missing')

# B) Convert the left track controls from separate cards into one continuous rail.
controls_anchor='''            ForEach(0..<model.trackCount,id:\\.self){lane in\n                let top=laneTop(lane),laneH=laneHeight(lane),panelW:CGFloat=118'''
unified='''            let railTop=laneTop(0)\n            let railLast=max(0,model.trackCount-1)\n            let railBottom=laneTop(railLast)+laneHeight(railLast)\n            RoundedRectangle(cornerRadius:15,style:.continuous)\n                .fill(Color(uiColor:.secondarySystemGroupedBackground).opacity(0.98))\n                .frame(width:118,height:max(36,railBottom-railTop))\n                .overlay(\n                    RoundedRectangle(cornerRadius:15,style:.continuous)\n                        .stroke(Color.primary.opacity(0.08),lineWidth:0.7)\n                )\n                .shadow(color:Color.black.opacity(0.07),radius:5,y:2)\n                .position(x:59,y:(railTop+railBottom)/2)\n                .zIndex(39)\n\n            ForEach(0..<model.trackCount,id:\\.self){lane in\n                let top=laneTop(lane),laneH=laneHeight(lane),panelW:CGFloat=118'''
if controls_anchor not in s:
    raise RuntimeError('compact track controls anchor missing')
s=s.replace(controls_anchor,unified,1)

old_shell='''                    RoundedRectangle(cornerRadius:13,style:.continuous)\n                        .fill(Color(uiColor:.secondarySystemGroupedBackground).opacity(0.98))\n                        .frame(width:panelW,height:max(34,laneH-5))\n                        .overlay(\n                            RoundedRectangle(cornerRadius:13,style:.continuous)\n                                .stroke(Color.primary.opacity(0.085),lineWidth:0.7)\n                        )\n                        .shadow(color:Color.black.opacity(0.08),radius:5,y:2)'''
new_shell='''                    Rectangle()\n                        .fill(Color.clear)\n                        .frame(width:panelW,height:max(34,laneH))'''
if old_shell not in s:
    raise RuntimeError('v0.5.8 per-lane shell missing')
s=s.replace(old_shell,new_shell,1)

main.write_text(s)

# C) Resize handle: no full divider; only two short centered lines between lanes.
enh=Path('VeloCutAI/VeloCutAI/VeloCutV4Enhancements.swift')
e=enh.read_text()
old='Capsule().fill(Color.secondary.opacity(0.55)).frame(width: 18, height: 3)'
new='''VStack(spacing: 2) {\n                Capsule().fill(Color.secondary.opacity(0.48)).frame(width: 16, height: 2)\n                Capsule().fill(Color.secondary.opacity(0.48)).frame(width: 16, height: 2)\n            }'''
if old not in e:
    raise RuntimeError('v0.5.8 lane resize capsule missing')
e=e.replace(old,new,1)
enh.write_text(e)

print('Applied v0.5.9 unified track rail, short double resize handles, and live audio drag preview')
