from pathlib import Path
import re

main=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=main.read_text()

# VeloCut v0.5.8
# 1) Keep timeline vertically fixed while a video/audio item is actively being moved.
scroll_anchor='''        .frame(minHeight:180,maxHeight:.infinity)\n        .background(Color(uiColor:.secondarySystemGroupedBackground))'''
scroll_repl='''        .frame(minHeight:180,maxHeight:.infinity)\n        .scrollDisabled(model.isMovingTimelineItem)\n        .background(Color(uiColor:.secondarySystemGroupedBackground))'''
if scroll_anchor not in s:
    raise RuntimeError('timeline vertical ScrollView anchor missing')
s=s.replace(scroll_anchor,scroll_repl,1)

# 2) Give selected audio the same clear selection affordance as video.
# v0.5.7 leaves this exact audio position modifier immediately before its tap/drag gestures.
audio_position='''.position(x:x,y:top+laneH/2)\n                    .onTapGesture{model.selectAudioClip(a.id)}'''
audio_selected='''.overlay(\n                        RoundedRectangle(cornerRadius:6)\n                            .stroke(Color.accentColor,lineWidth:model.selectedAudioClipID==a.id ? 2.5 : 0)\n                    )\n                    .shadow(color:model.selectedAudioClipID==a.id ? Color.accentColor.opacity(0.28) : .clear,radius:3)\n                    .scaleEffect(model.selectedAudioClipID==a.id ? 1.015 : 1)\n                    .animation(.easeOut(duration:0.14),value:model.selectedAudioClipID)\n                    .position(x:x,y:top+laneH/2)\n                    .onTapGesture{model.selectAudioClip(a.id)}'''
if audio_position not in s:
    raise RuntimeError('v0.5.7 audio selection anchor missing')
s=s.replace(audio_position,audio_selected,1)

# 3) Compact, separated iPhone-like track-control rail.
# Keep all existing actions; only replace the visual shell/sizing and B -> Cyrillic M.
s,n=re.subn(r'let top=laneTop\(lane\),laneH=laneHeight\(lane\),panelW:CGFloat=154',
            'let top=laneTop(lane),laneH=laneHeight(lane),panelW:CGFloat=118',s,count=1)
if n!=1:
    raise RuntimeError('track panel width anchor missing')

old_shell='''                    Rectangle()\n                        .fill(Color(uiColor:.tertiarySystemGroupedBackground).opacity(0.98))\n                        .frame(width:panelW,height:max(32,laneH-1))\n                        .overlay(Rectangle().stroke(Color.primary.opacity(0.07),lineWidth:0.5))'''
new_shell='''                    RoundedRectangle(cornerRadius:13,style:.continuous)\n                        .fill(Color(uiColor:.secondarySystemGroupedBackground).opacity(0.98))\n                        .frame(width:panelW,height:max(34,laneH-5))\n                        .overlay(\n                            RoundedRectangle(cornerRadius:13,style:.continuous)\n                                .stroke(Color.primary.opacity(0.085),lineWidth:0.7)\n                        )\n                        .shadow(color:Color.black.opacity(0.08),radius:5,y:2)'''
if old_shell not in s:
    raise RuntimeError('track panel shell missing')
s=s.replace(old_shell,new_shell,1)

s=s.replace('HStack(spacing:3){','HStack(spacing:2){',1)

old_name='''.frame(width:39,height:26)\n                                .background(Color.primary.opacity(0.06))'''
new_name='''.frame(width:32,height:24)\n                                .background(Color.primary.opacity(0.055),in:RoundedRectangle(cornerRadius:7,style:.continuous))'''
if old_name not in s:
    raise RuntimeError('track name control missing')
s=s.replace(old_name,new_name,1)

old_b='''Text("B").font(.system(size:9,weight:.bold))\n                                .frame(width:22,height:26)\n                                .background(model.bypassedTracks.contains(lane) ? Color.orange.opacity(0.34):Color.primary.opacity(0.055))'''
new_b='''Text("М").font(.system(size:9,weight:.bold))\n                                .frame(width:20,height:24)\n                                .background(model.bypassedTracks.contains(lane) ? Color.orange.opacity(0.30):Color.primary.opacity(0.05),in:RoundedRectangle(cornerRadius:7,style:.continuous))'''
if old_b not in s:
    raise RuntimeError('B control missing')
s=s.replace(old_b,new_b,1)

old_mute='''.frame(width:24,height:26)\n                                .background(model.mutedTracks.contains(lane) ? Color.red.opacity(0.20):Color.primary.opacity(0.055))'''
new_mute='''.frame(width:20,height:24)\n                                .background(model.mutedTracks.contains(lane) ? Color.red.opacity(0.18):Color.primary.opacity(0.05),in:RoundedRectangle(cornerRadius:7,style:.continuous))'''
if old_mute not in s:
    raise RuntimeError('mute control missing')
s=s.replace(old_mute,new_mute,1)

old_plus='''.frame(width:24,height:26)\n                                .background(Color.accentColor.opacity(0.16))'''
new_plus='''.frame(width:20,height:24)\n                                .background(Color.accentColor.opacity(0.14),in:RoundedRectangle(cornerRadius:7,style:.continuous))'''
if old_plus not in s:
    raise RuntimeError('track plus control missing')
s=s.replace(old_plus,new_plus,1)

old_chev='''.frame(width:22,height:26)\n                                .background(Color.primary.opacity(0.055))'''
new_chev='''.frame(width:18,height:24)\n                                .background(Color.primary.opacity(0.05),in:RoundedRectangle(cornerRadius:7,style:.continuous))'''
if old_chev not in s:
    raise RuntimeError('track chevron control missing')
s=s.replace(old_chev,new_chev,1)

# Panel center and resize handle follow the new compact width.
s=s.replace('.position(x:77,y:top+laneH/2)', '.position(x:59,y:top+laneH/2)',1)
s=s.replace('.position(x:146,y:top+laneH-6)', '.position(x:112,y:top+laneH-6)',1)

main.write_text(s)
print('Applied v0.5.8 fixed drag scroll, audio selection highlight and compact iPhone-style track rail')
