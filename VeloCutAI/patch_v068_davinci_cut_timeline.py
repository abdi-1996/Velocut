from pathlib import Path

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# VeloCut v0.6.3 — DaVinci-inspired Cut workspace.
# Keep the proven media/edit/export engine from v0.6.2 and rebuild the timeline
# interaction around a fixed center playhead, direct lanes and edge trim handles.

def block(start: str, end: str, new: str):
    global s
    i = s.find(start)
    if i < 0:
        raise RuntimeError(f'start marker missing: {start}')
    j = s.find(end, i + len(start))
    if j < 0:
        raise RuntimeError(f'end marker missing after: {start}')
    s = s[:i] + new.rstrip() + "\n\n" + s[j:]

block(
'    private var freshTimelineHeader:some View {',
'    private var freshVideoLaneCount:Int {',
'''    private var freshTimelineHeader:some View {
        ZStack {
            Color(red:0.09,green:0.09,blue:0.09)
            TimelineRulerV4(projectTime:model.projectTime,duration:model.projectDuration,pps:40*model.timelineZoom)
                .frame(height:28)
                .foregroundStyle(Color.white.opacity(0.70))
            HStack(spacing:10) {
                Text(String(format:"%02d:%02d.%02d", Int(model.projectTime)/60, Int(model.projectTime)%60, Int((model.projectTime.truncatingRemainder(dividingBy:1))*100)))
                    .font(.system(size:11,weight:.semibold,design:.monospaced))
                    .foregroundStyle(.white)
                    .padding(.horizontal,9)
                    .frame(height:24)
                    .background(Color.black.opacity(0.42),in:Capsule())
                Spacer()
                Button{model.timelineZoom=max(0.55,model.timelineZoom-0.18)}label:{Image(systemName:"minus.magnifyingglass")}
                Button{model.timelineZoom=min(3.2,model.timelineZoom+0.18)}label:{Image(systemName:"plus.magnifyingglass")}
            }
            .font(.system(size:12,weight:.medium))
            .foregroundStyle(Color.white.opacity(0.78))
            .padding(.horizontal,10)
        }
        .frame(height:32)
        .overlay(alignment:.bottom){Rectangle().fill(Color.black.opacity(0.55)).frame(height:0.7)}
    }''')

block(
'    private var freshTimelineContentHeight:CGFloat {',
'    private var freshGroupedTimeline:some View {',
'''    private var freshTimelineContentHeight:CGFloat {
        let video = CGFloat(max(1,freshVideoLaneCount) * 64)
        let audio = CGFloat(max(1,freshAudioLaneCount) * 52)
        let speed = CGFloat(52)
        let text = CGFloat(52)
        return max(260,video + audio + speed + text + 18)
    }''')

block(
'    private var freshGroupedTimeline:some View {',
'    private var freshTrackRail:some View {',
'''    private var freshGroupedTimeline:some View {
        GeometryReader{geo in
            ScrollView(.vertical,showsIndicators:false){
                freshTimelineRows(width:max(220,geo.size.width))
                    .frame(width:max(220,geo.size.width),height:freshTimelineContentHeight,alignment:.top)
            }
            .scrollDisabled(model.isMovingTimelineItem)
            .background(Color(red:0.12,green:0.12,blue:0.12))
        }
    }''')

block(
'    private func freshTimelineRows(width:CGFloat)->some View {',
'    private func freshMainSummaryRow(kind:String,accent:Color,width:CGFloat)->some View {',
'''    private func freshTimelineRows(width:CGFloat)->some View {
        ZStack(alignment:.topLeading){
            VStack(spacing:4){
                freshVideoTimelineRow(lane:0,width:width)
                if freshVideoLaneCount > 1 {
                    ForEach(1..<freshVideoLaneCount,id:\\.self){lane in
                        freshVideoTimelineRow(lane:lane,width:width)
                    }
                }
                freshAudioTimelineRow(lane:0,width:width)
                if freshAudioLaneCount > 1 {
                    ForEach(1..<freshAudioLaneCount,id:\\.self){lane in
                        freshAudioTimelineRow(lane:lane,width:width)
                    }
                }
                freshFXTimelineRow(lane:0,width:width)
                freshTextTimelineRow(lane:0,width:width)
            }

            Rectangle()
                .fill(Color.white.opacity(0.92))
                .frame(width:1.25,height:freshTimelineContentHeight)
                .position(x:width/2,y:freshTimelineContentHeight/2)
                .allowsHitTesting(false)
                .zIndex(500)

            Circle()
                .fill(Color.white)
                .frame(width:10,height:10)
                .position(x:width/2,y:5)
                .allowsHitTesting(false)
                .zIndex(501)
        }
        .background(Color(red:0.12,green:0.12,blue:0.12))
        .contentShape(Rectangle())
        .simultaneousGesture(
            DragGesture(minimumDistance:12)
                .onChanged{v in
                    if timelineDragStart==nil{timelineDragStart=model.projectTime;model.beginScrub()}
                    let pps=40.0*model.timelineZoom
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/max(1,pps))
                }
                .onEnded{_ in timelineDragStart=nil;model.endScrub()}
        )
        .simultaneousGesture(
            MagnificationGesture()
                .onChanged{v in
                    if freshZoomStart==nil{freshZoomStart=model.timelineZoom}
                    model.timelineZoom=min(3.2,max(0.55,(freshZoomStart ?? model.timelineZoom)*Double(v)))
                }
                .onEnded{_ in freshZoomStart=nil}
        )
        .clipped()
    }''')

block(
'    private func freshVideoTimelineRow(lane:Int,width:CGFloat)->some View {',
'    private func freshAudioTimelineRow(lane:Int,width:CGFloat)->some View {',
'''    private func freshVideoTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(red:0.12,green:0.12,blue:0.12))
            Rectangle().fill(Color.black.opacity(0.32)).frame(height:0.7).offset(y:63.3)
            ForEach(Array(model.layouts.enumerated()).filter{$0.element.clip.track==lane},id:\\.element.id){_,l in
                let w=max(52,CGFloat(l.duration*pps))
                let x=center+CGFloat((l.start-model.projectTime)*pps)+w/2
                FreshVideoClipCardV065(
                    name:l.clip.name,
                    width:w,
                    color:v060TrackColor(lane),
                    selected:model.selectedClipID==l.id,
                    onTap:{model.selectClip(l.id)},
                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{model.moveClip(l.id,translation:$0,pps:pps)},
                    onTrimLeft:{dx in
                        model.selectedClipID=l.id
                        let sourceDelta=Double(dx)/max(1,pps)*max(0.1,l.clip.baseSpeed)
                        model.setTrimStart(l.clip.trimStart+sourceDelta)
                        model.haptic(.selection)
                    },
                    onTrimRight:{dx in
                        model.selectedClipID=l.id
                        let sourceDelta=Double(dx)/max(1,pps)*max(0.1,l.clip.baseSpeed)
                        model.setTrimEnd(l.clip.trimEnd+sourceDelta)
                        model.haptic(.selection)
                    }
                )
                .position(x:x,y:32)
            }
        }.frame(height:64).clipped()
    }''')

block(
'    private var freshBottomToolbar:some View {',
'    private func freshTool(_ icon:String,_ title:String,_ tool:InspectorTool)->some View {',
'''    private var freshBottomToolbar:some View {
        VStack(spacing:0){
            ScrollView(.horizontal,showsIndicators:false){
                HStack(spacing:5){
                    freshActionTool("scissors","Cut",selected:true){}
                    freshActionTool("rectangle.compress.vertical","Trim"){inspector = .trim}
                    freshActionTool("scissors","Split"){model.splitAtPlayhead()}
                    freshActionTool("trash","Delete"){
                        if let id=model.selectedClipID{model.deleteClip(id)}
                    }
                    freshActionTool("speedometer","Speed"){inspector = .speed}
                    freshActionTool("speaker.wave.2","Volume"){inspector = .audio}
                    freshActionTool("plus.square.on.square","Duplicate"){
                        if let id=model.selectedClipID{model.duplicateClip(id)}
                    }
                }
                .padding(.horizontal,10)
                .padding(.vertical,7)
            }
            .frame(height:66)

            Rectangle().fill(Color.black.opacity(0.38)).frame(height:0.7)

            ScrollView(.horizontal,showsIndicators:false){
                HStack(spacing:5){
                    freshActionTool("photo","Media"){v060AddVideoMedia()}
                    freshActionTool("music.note","Audio"){v060AddAudio()}
                    freshActionTool("textformat","Text"){v060AddText()}
                    freshActionTool("sparkles","Effects"){v060AddFX()}
                    freshActionTool("arrow.left.and.right.square","Transitions"){inspector = .filters}
                    freshActionTool("camera.filters","Filters"){inspector = .filters}
                    freshActionTool("slider.horizontal.3","Adjust"){inspector = .adjust}
                }
                .padding(.horizontal,10)
                .padding(.vertical,7)
            }
            .frame(height:66)
        }
        .frame(height:133)
        .background(Color(red:0.10,green:0.10,blue:0.10))
        .overlay(alignment:.top){Rectangle().fill(Color.black.opacity(0.55)).frame(height:0.7)}
    }

    private func freshActionTool(_ icon:String,_ title:String,selected:Bool=false,action:@escaping()->Void)->some View {
        Button(action:action){
            VStack(spacing:4){
                Image(systemName:icon).font(.system(size:17,weight:.medium))
                Text(title).font(.system(size:9,weight:selected ? .semibold:.medium)).lineLimit(1)
            }
            .foregroundStyle(selected ? Color(red:0.67,green:0.38,blue:1.0):Color.white.opacity(0.90))
            .frame(width:68,height:50)
            .background(selected ? Color.white.opacity(0.05):Color.clear,in:RoundedRectangle(cornerRadius:10))
            .overlay(alignment:.bottom){
                if selected { Capsule().fill(Color(red:0.67,green:0.38,blue:1.0)).frame(width:28,height:2.5) }
            }
        }
        .buttonStyle(.plain)
    }''')

block(
'struct FreshVideoClipCardV065:View{',
'struct FreshAudioClipCardV065:View{',
'''struct FreshVideoClipCardV065:View{
    let name:String
    let width:CGFloat
    let color:Color
    let selected:Bool
    let onTap:()->Void
    let onMenu:()->Void
    let onMove:(CGSize)->Void
    let onTrimLeft:(CGFloat)->Void
    let onTrimRight:(CGFloat)->Void
    @State private var drag:CGSize = .zero
    @State private var leftTrimPreview:CGFloat = 0
    @State private var rightTrimPreview:CGFloat = 0

    var body:some View{
        ZStack{
            HStack(spacing:5){
                Image(systemName:"film").font(.system(size:10,weight:.semibold))
                Text(name).font(.system(size:9,weight:.semibold)).lineLimit(1)
                Spacer(minLength:0)
            }
            .foregroundStyle(.white)
            .padding(.horizontal,selected ? 17:7)
            .frame(width:width,height:42)
            .background(color.opacity(0.90),in:RoundedRectangle(cornerRadius:7))
            .overlay(RoundedRectangle(cornerRadius:7).stroke(selected ? Color.white:Color.clear,lineWidth:2))
            .shadow(color:selected ? Color.black.opacity(0.24):.clear,radius:3)
            .offset(drag)
            .contentShape(Rectangle())
            .onTapGesture{onTap()}
            .highPriorityGesture(
                LongPressGesture(minimumDuration:0.30).sequenced(before:DragGesture(minimumDistance:0))
                    .onChanged{v in if case .second(true,let d?)=v{drag=d.translation}}
                    .onEnded{v in
                        defer{drag = .zero}
                        if case .second(true,let d?)=v{
                            if hypot(d.translation.width,d.translation.height)<8{onMenu()}else{onMove(d.translation)}
                        }else{onMenu()}
                    }
            )

            if selected {
                HStack(spacing:0){
                    RoundedRectangle(cornerRadius:5)
                        .fill(Color.white)
                        .frame(width:14,height:46)
                        .overlay(Capsule().fill(Color(red:0.67,green:0.38,blue:1.0)).frame(width:2.5,height:18))
                        .offset(x:leftTrimPreview)
                        .highPriorityGesture(
                            DragGesture(minimumDistance:0)
                                .onChanged{v in leftTrimPreview=min(max(v.translation.width,-width+32),width-32)}
                                .onEnded{v in onTrimLeft(v.translation.width);leftTrimPreview = 0}
                        )
                    Spacer(minLength:0)
                    RoundedRectangle(cornerRadius:5)
                        .fill(Color.white)
                        .frame(width:14,height:46)
                        .overlay(Capsule().fill(Color(red:0.67,green:0.38,blue:1.0)).frame(width:2.5,height:18))
                        .offset(x:rightTrimPreview)
                        .highPriorityGesture(
                            DragGesture(minimumDistance:0)
                                .onChanged{v in rightTrimPreview=min(max(v.translation.width,-width+32),width-32)}
                                .onEnded{v in onTrimRight(v.translation.width);rightTrimPreview = 0}
                        )
                }
                .frame(width:width,height:46)
                .zIndex(20)
            }
        }
        .frame(width:width,height:46)
    }
}
''')

p.write_text(s)
print('Applied VeloCut v0.6.3 DaVinci Cut timeline')
