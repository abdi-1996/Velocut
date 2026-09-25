from pathlib import Path
import re

main=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=main.read_text()

# VeloCut v0.5.7 interaction-only fix:
# - selection context resets correctly
# - clips move only after long press
# - moving an item does not scrub the timeline
# - audio/video snap to lanes, edit joints and playhead

state='@Published var selectedAudioClipID: UUID?'
if state not in s: raise RuntimeError('selectedAudioClipID state missing')
s=s.replace(state,state+'\n    @Published var timelineItemDragActive = false',1)

anchor='    func addTrack() {'
if anchor not in s: raise RuntimeError('addTrack helper anchor missing')
helpers=r'''    func clearTimelineSelection() {
        selectedAudioClipID=nil
        selectedClipID=nil
    }

    func setTimelineItemDrag(_ active:Bool) {
        if timelineItemDragActive == active { return }
        timelineItemDragActive=active
        if active {
            player.pause(); isPlaying=false
            haptic(.medium)
        }
    }

    private func timelineSnapPoints(excludingAudio audioID:UUID?=nil, excludingClip clipID:UUID?=nil)->[Double] {
        var points:[Double]=[0,projectTime]
        for l in layouts where l.id != clipID { points.append(l.start);points.append(l.end) }
        for a in audioClips where a.id != audioID { points.append(a.start);points.append(a.end) }
        return points
    }

    func moveAudioClipSnapped(_ id:UUID,translation:CGSize,pps:Double) {
        guard let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let original=audioClips[i]
        var start=max(0,original.start+Double(translation.width)/max(1,pps))
        let targetLane=min(max(0,trackCount-1),max(0,original.track+Int((translation.height/52).rounded())))
        let threshold=max(0.055,Double(11/max(20,pps)))
        var bestDelta:Double?
        var bestDistance=Double.greatestFiniteMagnitude
        for point in timelineSnapPoints(excludingAudio:id) {
            for edge in [start,start+original.duration] {
                let delta=point-edge,dist=abs(delta)
                if dist<=threshold && dist<bestDistance {bestDistance=dist;bestDelta=delta}
            }
        }
        let snapped=bestDelta != nil
        if let d=bestDelta {start=max(0,start+d)}
        guard abs(start-original.start)>0.001 || targetLane != original.track else{return}
        registerUndo()
        audioClips[i].start=start
        audioClips[i].track=targetLane
        selectedAudioClipID=id;selectedClipID=nil
        schedulePreview(immediate:true)
        haptic(snapped || targetLane != original.track ? .selection:.light)
    }

    func moveClipSnapped(_ id:UUID,translation:CGSize,pps:Double) {
        guard let sourceIndex=clips.firstIndex(where:{$0.id==id}),let current=layout(for:id) else{return}
        let original=clips[sourceIndex]
        let targetLane=min(max(0,trackCount-1),max(0,original.track+Int((translation.height/52).rounded())))
        let proposed=max(0,current.start+Double(translation.width)/max(1,pps))
        let threshold=max(0.055,Double(12/max(20,pps)))
        let points=timelineSnapPoints(excludingClip:id)
        let nearest=points.min(by:{abs($0-proposed)<abs($1-proposed)})
        let snappedTime=(nearest != nil && abs((nearest ?? proposed)-proposed)<=threshold) ? nearest : nil
        var targetIndex:Int
        if let t=snappedTime {
            let ordered=layouts.filter{$0.id != id}
            targetIndex=ordered.firstIndex(where:{$0.start>=t-0.001}) ?? ordered.count
        } else {
            let step=max(46.0,pps)
            targetIndex=min(max(0,sourceIndex+Int((translation.width/step).rounded())),max(0,clips.count-1))
        }
        guard targetIndex != sourceIndex || targetLane != original.track else{return}
        registerUndo()
        var moved=clips.remove(at:sourceIndex)
        moved.track=targetLane
        clips.insert(moved,at:min(max(0,targetIndex),clips.count))
        selectedAudioClipID=nil;selectedClipID=moved.id
        schedulePreview(immediate:true)
        haptic(snappedTime != nil || targetLane != original.track ? .selection:.light)
    }

'''
s=s.replace(anchor,helpers+anchor,1)

bg='ZStack(alignment:.topLeading){RoundedRectangle(cornerRadius:6).fill(Color(uiColor:.secondarySystemGroupedBackground));TimelineRulerV4'
if bg not in s: raise RuntimeError('timeline background anchor missing')
s=s.replace(bg,'ZStack(alignment:.topLeading){RoundedRectangle(cornerRadius:6).fill(Color(uiColor:.secondarySystemGroupedBackground)).contentShape(Rectangle()).onTapGesture{model.clearTimelineSelection()};TimelineRulerV4',1)

old='''                .onChanged{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)
                }
                .onEnded{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else {
                        if timelineDragStart != nil { timelineDragStart=nil;model.endScrub() }
                        return
                    }
                    timelineDragStart=nil
                    model.endScrub()
                }'''
new='''                .onChanged{v in
                    guard !model.timelineItemDragActive else { return }
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)
                }
                .onEnded{v in
                    if model.timelineItemDragActive {
                        if timelineDragStart != nil {timelineDragStart=nil;model.endScrub()}
                        return
                    }
                    guard abs(v.translation.width) > abs(v.translation.height) else {
                        if timelineDragStart != nil { timelineDragStart=nil;model.endScrub() }
                        return
                    }
                    timelineDragStart=nil
                    model.endScrub()
                }'''
if old not in s: raise RuntimeError('v0.5.6 timeline scrub body missing')
s=s.replace(old,new,1)

old_call='''                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{if !multiSelectMode{model.moveClip(l.id,translation:$0,pps:pps)}}
                )'''
new_call='''                    onMenu:{model.selectedAudioClipID=nil;model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{if !multiSelectMode{model.moveClipSnapped(l.id,translation:$0,pps:pps)}},
                    onDragStateChanged:{active in model.setTimelineItemDrag(active)}
                )'''
if old_call not in s: raise RuntimeError('Filmstrip callback block missing')
s=s.replace(old_call,new_call,1)

old_audio='''.onTapGesture{model.selectAudioClip(a.id)}.highPriorityGesture(LongPressGesture(minimumDuration:0.28).sequenced(before:DragGesture(minimumDistance:0)).onEnded{v in if case .second(true,let d?)=v{if hypot(d.translation.width,d.translation.height)<8{model.deleteAudioClip(a.id)}else{model.moveAudioClip(a.id,translation:d.translation,pps:pps)}}})'''
new_audio='''.onTapGesture{model.selectAudioClip(a.id)}.highPriorityGesture(
                    LongPressGesture(minimumDuration:0.32)
                        .sequenced(before:DragGesture(minimumDistance:0))
                        .onChanged{v in
                            switch v {
                            case .first(true): model.setTimelineItemDrag(true);model.selectAudioClip(a.id)
                            case .second(true,_): model.setTimelineItemDrag(true)
                            default: break
                            }
                        }
                        .onEnded{v in
                            defer{model.setTimelineItemDrag(false)}
                            if case .second(true,let d?)=v,hypot(d.translation.width,d.translation.height)>=4 {
                                model.moveAudioClipSnapped(a.id,translation:d.translation,pps:pps)
                            }
                        }
                )'''
if old_audio not in s: raise RuntimeError('inline audio long-press gesture missing')
s=s.replace(old_audio,new_audio,1)
main.write_text(s)

enh=Path('VeloCutAI/VeloCutAI/VeloCutV4Enhancements.swift')
e=enh.read_text()
field='''    let onMenu: () -> Void
    let onMove: (CGSize) -> Void
    @State private var drag: CGSize = .zero'''
field_new='''    let onMenu: () -> Void
    let onMove: (CGSize) -> Void
    let onDragStateChanged: (Bool) -> Void
    @State private var drag: CGSize = .zero
    @State private var dragArmed = false'''
if field not in e: raise RuntimeError('Filmstrip callback fields missing')
e=e.replace(field,field_new,1)

start=e.find('struct FilmstripClipCardV45: View')
if start<0: raise RuntimeError('FilmstripClipCardV45 missing')
head,tail=e[:start],e[start:]
gesture_pat=re.compile(r'''        \.highPriorityGesture\(\s*\n            LongPressGesture\(minimumDuration: 0\.32\)\s*\n                \.sequenced\(before: DragGesture\(minimumDistance: 0\)\)\s*\n                \.onChanged \{ value in.*?\n        \)''',re.S)
gesture_new='''        .highPriorityGesture(
            LongPressGesture(minimumDuration: 0.32)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    switch value {
                    case .first(true):
                        if !dragArmed { dragArmed=true;onDragStateChanged(true);onTap() }
                    case .second(true, let gesture):
                        if !dragArmed { dragArmed=true;onDragStateChanged(true);onTap() }
                        if let gesture { drag = gesture.translation }
                    default: break
                    }
                }
                .onEnded { value in
                    defer {
                        drag = .zero
                        if dragArmed {dragArmed=false;onDragStateChanged(false)}
                    }
                    if case .second(true, let gesture) = value, let gesture {
                        if hypot(gesture.translation.width, gesture.translation.height) >= 4 {onMove(gesture.translation)}
                    }
                }
        )'''
tail,n=gesture_pat.subn(gesture_new,tail,count=1)
if n!=1: raise RuntimeError('Filmstrip structural long-press gesture missing')
e=head+tail
enh.write_text(e)
print('Applied v0.5.7 selection reset, long-press-only movement and magnetic snapping')
