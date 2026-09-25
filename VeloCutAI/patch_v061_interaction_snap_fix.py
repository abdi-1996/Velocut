from pathlib import Path
import re

main=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=main.read_text()

# VeloCut v0.5.7: selection, long-press moving, gesture isolation and magnetic snapping.

# 1) Shared moving state prevents the parent timeline scrub from moving while an item is being dragged.
state='@Published var trackCount: Int = 3'
if state not in s:
    raise RuntimeError('trackCount state missing')
s=s.replace(state,state+'\n    @Published var isMovingTimelineItem = false',1)

method_anchor='''    func toggleTrackMute(_ lane:Int) {
        if mutedTracks.contains(lane){mutedTracks.remove(lane)}else{mutedTracks.insert(lane)}
        schedulePreview(immediate:true)
    }
'''
if method_anchor not in s:
    raise RuntimeError('toggleTrackMute method missing')
method_extra=r'''

    func beginTimelineItemMove() {
        if !isMovingTimelineItem {
            isMovingTimelineItem=true
            player.pause(); isPlaying=false
            haptic(.selection)
        }
    }

    func endTimelineItemMove() {
        isMovingTimelineItem=false
    }

    func clearTimelineSelection() {
        selectedAudioClipID=nil
        selectedClipID=nil
    }
'''
s=s.replace(method_anchor,method_anchor+method_extra,1)

# 2) Video movement: after a long press, choose the nearest insertion joint and snap to a lane.
move_clip_pat=re.compile(r'    func moveClip\(_ id: UUID, translation: CGSize, pps: Double\) \{.*?\n    \}',re.S)
move_clip_repl=r'''    func moveClip(_ id: UUID, translation: CGSize, pps: Double) {
        guard let sourceIndex=clips.firstIndex(where:{$0.id==id}),let current=layout(for:id) else{return}
        let safePPS=max(1,pps)
        let proposedStart=max(0,current.start+Double(translation.width)/safePPS)
        let before=layouts.filter{$0.id != id}
        var joints:[Double]=[0]
        joints.append(contentsOf:before.map{$0.end})
        var targetIndex=joints.enumerated().min(by:{abs($0.element-proposedStart)<abs($1.element-proposedStart)})?.offset ?? sourceIndex
        targetIndex=min(max(0,targetIndex),max(0,clips.count-1))
        let laneDelta=Int((translation.height/52).rounded())
        let targetTrack=min(max(0,trackCount-1),max(0,clips[sourceIndex].track+laneDelta))
        guard targetIndex != sourceIndex || targetTrack != clips[sourceIndex].track else{return}
        registerUndo()
        var item=clips.remove(at:sourceIndex)
        item.track=targetTrack
        let insertion=min(max(0,targetIndex),clips.count)
        clips.insert(item,at:insertion)
        selectedAudioClipID=nil
        selectedClipID=item.id
        schedulePreview(immediate:true)
        haptic(.selection)
    }'''
s,n=move_clip_pat.subn(move_clip_repl,s,count=1)
if n!=1:
    raise RuntimeError('moveClip method missing')

# 3) Audio movement keeps free time placement, but magnetically snaps to video/audio joints and playhead.
move_audio_pat=re.compile(r'    func moveAudioClip\(_ id: UUID, translation: CGSize, pps: Double\) \{.*?\n    \}',re.S)
move_audio_repl=r'''    func moveAudioClip(_ id: UUID, translation: CGSize, pps: Double) {
        guard let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let original=audioClips[i],safePPS=max(1,pps),threshold=10.0/safePPS
        var proposed=max(0,original.start+Double(translation.width)/safePPS)
        var candidates:[Double]=[0,projectTime]
        candidates.append(contentsOf:layouts.flatMap{[$0.start,$0.end]})
        candidates.append(contentsOf:audioClips.filter{$0.id != id}.flatMap{[$0.start,$0.end]})
        var bestStart=proposed,bestDistance=threshold+0.0001
        for point in candidates {
            let startDistance=abs(proposed-point)
            if startDistance<bestDistance {bestDistance=startDistance;bestStart=point}
            let endDistance=abs((proposed+original.duration)-point)
            if endDistance<bestDistance {bestDistance=endDistance;bestStart=max(0,point-original.duration)}
        }
        if bestDistance<=threshold {proposed=bestStart;haptic(.selection)}
        audioClips[i].start=proposed
        let laneDelta=Int((translation.height/52).rounded())
        audioClips[i].track=min(max(0,trackCount-1),max(0,original.track+laneDelta))
        selectedClipID=nil
        selectedAudioClipID=id
        schedulePreview()
    }'''
s,n=move_audio_pat.subn(move_audio_repl,s,count=1)
if n!=1:
    raise RuntimeError('moveAudioClip method missing')

# 4) Tap on empty lane removes audio/video selection so the bottom toolbar returns to the normal state.
old_lane_bg='''                Rectangle()
                    .fill(Color.secondary.opacity(0.055))
                    .frame(height:max(32,laneH-1))
                    .offset(y:top)'''
new_lane_bg='''                Rectangle()
                    .fill(Color.secondary.opacity(0.055))
                    .frame(height:max(32,laneH-1))
                    .offset(y:top)
                    .contentShape(Rectangle())
                    .onTapGesture{model.clearTimelineSelection()}'''
if old_lane_bg not in s:
    raise RuntimeError('lane background block missing')
s=s.replace(old_lane_bg,new_lane_bg,1)

# 5) Parent horizontal scrub ignores a clip/audio drag once long-press moving is armed.
old_changed='''                .onChanged{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }'''
new_changed='''                .onChanged{v in
                    guard !model.isMovingTimelineItem else {
                        if timelineDragStart != nil { timelineDragStart=nil;model.endScrub() }
                        return
                    }
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }'''
if old_changed not in s:
    raise RuntimeError('timeline onChanged block missing')
s=s.replace(old_changed,new_changed,1)

old_ended='''                .onEnded{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else {'''
new_ended='''                .onEnded{v in
                    if model.isMovingTimelineItem {
                        if timelineDragStart != nil { timelineDragStart=nil;model.endScrub() }
                        return
                    }
                    guard abs(v.translation.width) > abs(v.translation.height) else {'''
if old_ended not in s:
    raise RuntimeError('timeline onEnded block missing')
s=s.replace(old_ended,new_ended,1)

# 6) Magnetic preview helpers. Horizontal edges snap within ~10pt; vertical motion lands exactly on lanes.
helper_anchor='    private var timelineRequiredHeight:CGFloat {'
if helper_anchor not in s:
    raise RuntimeError('timelineRequiredHeight anchor missing')
helpers=r'''    private func snappedVideoTranslation(_ item:ClipLayout,_ raw:CGSize,pps:Double)->CGSize {
        let safePPS=max(1,pps),threshold=10.0/safePPS
        var desired=max(0,item.start+Double(raw.width)/safePPS)
        var candidates:[Double]=[0,model.projectTime]
        candidates.append(contentsOf:model.layouts.filter{$0.id != item.id}.flatMap{[$0.start,$0.end]})
        candidates.append(contentsOf:model.audioClips.flatMap{[$0.start,$0.end]})
        var best=desired,bestDistance=threshold+0.0001
        for point in candidates {
            let ds=abs(desired-point)
            if ds<bestDistance {bestDistance=ds;best=point}
            let de=abs((desired+item.duration)-point)
            if de<bestDistance {bestDistance=de;best=max(0,point-item.duration)}
        }
        if bestDistance<=threshold {desired=best}
        let laneDelta=Int((raw.height/52).rounded())
        let target=min(max(0,model.trackCount-1),max(0,item.clip.track+laneDelta))
        return CGSize(width:CGFloat((desired-item.start)*safePPS),height:CGFloat(target-item.clip.track)*52)
    }

    private func snappedAudioTranslation(_ item:TimelineAudioClip,_ raw:CGSize,pps:Double)->CGSize {
        let safePPS=max(1,pps),threshold=10.0/safePPS
        var desired=max(0,item.start+Double(raw.width)/safePPS)
        var candidates:[Double]=[0,model.projectTime]
        candidates.append(contentsOf:model.layouts.flatMap{[$0.start,$0.end]})
        candidates.append(contentsOf:model.audioClips.filter{$0.id != item.id}.flatMap{[$0.start,$0.end]})
        var best=desired,bestDistance=threshold+0.0001
        for point in candidates {
            let ds=abs(desired-point)
            if ds<bestDistance {bestDistance=ds;best=point}
            let de=abs((desired+item.duration)-point)
            if de<bestDistance {bestDistance=de;best=max(0,point-item.duration)}
        }
        if bestDistance<=threshold {desired=best}
        let laneDelta=Int((raw.height/52).rounded())
        let target=min(max(0,model.trackCount-1),max(0,item.track+laneDelta))
        return CGSize(width:CGFloat((desired-item.start)*safePPS),height:CGFloat(target-item.track)*52)
    }

'''
s=s.replace(helper_anchor,helpers+helper_anchor,1)

# 7) Video cards: tap selects video; long press arms move, vibrates and uses snapped visual translation.
old_video_call='''                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{if !multiSelectMode{model.moveClip(l.id,translation:$0,pps:pps)}}
                )'''
new_video_call='''                    onMenu:{model.selectedAudioClipID=nil;model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onPreviewMove:{snappedVideoTranslation(l,$0,pps:pps)},
                    onMoveState:{active in if active{model.beginTimelineItemMove()}else{model.endTimelineItemMove()}},
                    onMove:{if !multiSelectMode{model.moveClip(l.id,translation:$0,pps:pps)}}
                )'''
if old_video_call not in s:
    raise RuntimeError('FilmstripClipCard call block missing')
s=s.replace(old_video_call,new_video_call,1)

# 8) Audio cards: same long-press behavior and magnetic preview. A short tap only selects audio.
audio_pat=re.compile(r'\.position\(x:x,y:top\+laneH/2\)\.onTapGesture\{model\.selectAudioClip\(a\.id\)\}\.highPriorityGesture\(LongPressGesture\(minimumDuration:0\.28\)\.sequenced\(before:DragGesture\(minimumDistance:0\)\)\.onEnded\{v in if case \.second\(true,let d\?\)=v\{if hypot\(d\.translation\.width,d\.translation\.height\)<8\{model\.deleteAudioClip\(a\.id\)\}else\{model\.moveAudioClip\(a\.id,translation:d\.translation,pps:pps\)\}\}\}\)')
audio_repl='''.position(x:x,y:top+laneH/2)
                    .onTapGesture{model.selectAudioClip(a.id)}
                    .simultaneousGesture(
                        LongPressGesture(minimumDuration:0.30)
                            .sequenced(before:DragGesture(minimumDistance:0))
                            .onChanged{value in
                                if case .second(true,_)=value { model.beginTimelineItemMove() }
                            }
                            .onEnded{value in
                                defer{model.endTimelineItemMove()}
                                if case .second(true,let drag?)=value {
                                    let snapped=snappedAudioTranslation(a,drag.translation,pps:pps)
                                    if hypot(snapped.width,snapped.height)>=6 { model.moveAudioClip(a.id,translation:snapped,pps:pps) }
                                }
                            }
                    )'''
s,n=audio_pat.subn(audio_repl,s,count=1)
if n!=1:
    raise RuntimeError('audio card long press gesture missing')

main.write_text(s)

# 9) Filmstrip component exposes drag-preview/state callbacks. Ordinary taps remain independent.
ui=Path('VeloCutAI/VeloCutAI/VeloCutV45UI.swift')
u=ui.read_text()

old_props='''    let onTap: () -> Void
    let onMenu: () -> Void
    let onMove: (CGSize) -> Void
    @State private var drag: CGSize = .zero'''
new_props='''    let onTap: () -> Void
    let onMenu: () -> Void
    let onPreviewMove: (CGSize) -> CGSize
    let onMoveState: (Bool) -> Void
    let onMove: (CGSize) -> Void
    @State private var drag: CGSize = .zero
    @State private var moveArmed = false'''
if old_props not in u:
    raise RuntimeError('Filmstrip properties missing')
u=u.replace(old_props,new_props,1)

old_gesture='''        .highPriorityGesture(
            LongPressGesture(minimumDuration: 0.32)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    if case .second(true, let gesture) = value, let gesture { drag = gesture.translation }
                }
                .onEnded { value in
                    defer { drag = .zero }
                    if case .second(true, let gesture) = value, let gesture {
                        hypot(gesture.translation.width, gesture.translation.height) < 10 ? onMenu() : onMove(gesture.translation)
                    } else {
                        onMenu()
                    }
                }
        )'''
new_gesture='''        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.30)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    if case .second(true, let gesture) = value, let gesture {
                        if !moveArmed {
                            moveArmed = true
                            onMoveState(true)
                            UIImpactFeedbackGenerator(style: .light).impactOccurred()
                        }
                        drag = onPreviewMove(gesture.translation)
                    }
                }
                .onEnded { value in
                    defer {
                        drag = .zero
                        if moveArmed { onMoveState(false) }
                        moveArmed = false
                    }
                    if case .second(true, _) = value {
                        if hypot(drag.width, drag.height) >= 6 { onMove(drag) }
                    }
                }
        )'''
if old_gesture not in u:
    raise RuntimeError('Filmstrip long press gesture missing')
u=u.replace(old_gesture,new_gesture,1)
ui.write_text(u)

print('Applied v0.5.7 selection reset, isolated long-press moving and magnetic snapping')
