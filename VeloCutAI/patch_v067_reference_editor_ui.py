from pathlib import Path

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# v0.6.2 — rebuild the fresh workspace to match the user's reference mockups.
# Keep the existing editing engine and gestures; replace only the presentation.

def block(start: str, end: str, new: str):
    global s
    i=s.find(start)
    if i<0:
        raise RuntimeError(f'start marker missing: {start}')
    j=s.find(end,i+len(start))
    if j<0:
        raise RuntimeError(f'end marker missing after: {start}')
    s=s[:i]+new.rstrip()+"\n\n"+s[j:]

# Neutral unmodified subtrack color on the dark reference UI.
s=s.replace('default: return Color.primary.opacity(0.10)','default: return Color.white.opacity(0.18)',1)

block(
'    @ViewBuilder private func adaptiveWorkspace(_ root: GeometryProxy)->some View {',
'    private var workspaceHandle:',
'''    @ViewBuilder private func adaptiveWorkspace(_ root: GeometryProxy)->some View {
        VStack(spacing:0){
            freshPreviewArea(root)
                .frame(height:max(270,min(420,root.size.height*0.405)))
            freshTimelineHeader
            freshGroupedTimeline
                .frame(maxHeight:.infinity)
            freshBottomToolbar
        }
        .background(Color(red:0.135,green:0.135,blue:0.135))
        .preferredColorScheme(.dark)
    }''')

block(
'    private func freshPreviewArea(_ root:GeometryProxy)->some View {',
'    private var freshTimelineHeader:some View {',
'''    private func freshPreviewArea(_ root:GeometryProxy)->some View {
        ZStack{
            Color(red:0.135,green:0.135,blue:0.135)
            VStack(spacing:0){
                HStack{
                    Text("VeloCut")
                        .font(.system(size:24,weight:.bold,design:.rounded))
                        .foregroundStyle(.white)
                    Spacer()
                    Button{inspector = .export}label:{
                        Text("EXPORT")
                            .font(.system(size:12,weight:.semibold))
                            .foregroundStyle(model.clips.isEmpty ? Color.white.opacity(0.34):Color.white.opacity(0.86))
                            .padding(.horizontal,16)
                            .frame(height:32)
                            .background(Color.black.opacity(0.28),in:Capsule())
                            .overlay(Capsule().stroke(Color.black.opacity(0.35),lineWidth:0.7))
                    }
                    .buttonStyle(.plain)
                    .disabled(model.clips.isEmpty)
                }
                .padding(.horizontal,18)
                .frame(height:48)

                ZStack{
                    Color(red:0.135,green:0.135,blue:0.135)
                    if !model.clips.isEmpty {
                        PlayerView(player:model.player)
                            .clipped()
                        if !model.overlayText.isEmpty {
                            GeometryReader{g in
                                Text(model.overlayText)
                                    .font(.system(size:model.overlayTextSize,weight:.bold))
                                    .foregroundStyle(.white)
                                    .shadow(radius:4)
                                    .position(x:g.size.width/2,y:g.size.height*model.overlayTextY)
                            }
                        }
                    } else {
                        Button{v060AddVideoMedia()}label:{
                            ZStack{
                                Circle()
                                    .fill(Color.white.opacity(0.97))
                                    .frame(width:74,height:74)
                                    .shadow(color:.black.opacity(0.28),radius:5,y:3)
                                Image(systemName:"plus")
                                    .font(.system(size:36,weight:.medium))
                                    .foregroundStyle(.black)
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Добавить видео или фото")
                    }
                }
                .frame(maxWidth:.infinity,maxHeight:.infinity)

                ZStack{
                    Button{model.playPause()}label:{
                        Image(systemName:model.isPlaying ? "pause.fill":"play")
                            .font(.system(size:22,weight:.regular))
                            .foregroundStyle(.white)
                            .frame(width:48,height:38)
                    }
                    .buttonStyle(.plain)
                    .disabled(model.clips.isEmpty)

                    HStack(spacing:22){
                        Spacer()
                        Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward")}.disabled(!model.canUndo)
                        Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward")}.disabled(!model.canRedo)
                    }
                    .font(.system(size:20,weight:.medium))
                    .foregroundStyle(.white)
                    .padding(.trailing,18)
                }
                .frame(height:48)
                .overlay(alignment:.bottom){
                    Capsule().fill(Color.white.opacity(0.65)).frame(width:44,height:1.3).padding(.bottom,2)
                }
            }
        }
    }''')

block(
'    private var freshTimelineHeader:some View {',
'    private var freshVideoLaneCount:Int {',
'''    private var freshTimelineHeader:some View {
        ZStack{
            Color(red:0.105,green:0.105,blue:0.105)
            TimelineRulerV4(projectTime:model.projectTime,duration:model.projectDuration,pps:40*model.timelineZoom)
                .frame(height:28)
                .foregroundStyle(Color.white.opacity(0.72))
        }
        .frame(height:30)
        .overlay(alignment:.bottom){Rectangle().fill(Color.black.opacity(0.45)).frame(height:0.7)}
    }''')

block(
'    private var freshTimelineContentHeight:CGFloat {',
'    private var freshGroupedTimeline:some View {',
'''    private var freshTimelineContentHeight:CGFloat {
        let main=CGFloat(4*48)
        let v=videoGroupExpanded ? CGFloat(freshVideoLaneCount*56 + (freshVideoLaneCount>0 ? 26:0)):0
        let a=audioGroupExpanded ? CGFloat(freshAudioLaneCount*56 + (freshAudioLaneCount>0 ? 26:0)):0
        let t=textGroupExpanded ? CGFloat(freshTextLaneCount*56 + (freshTextLaneCount>0 ? 26:0)):0
        let f=fxGroupExpanded ? CGFloat(freshFXLaneCount*56 + (freshFXLaneCount>0 ? 26:0)):0
        return max(280,main+v+a+t+f)
    }''')

block(
'    private var freshGroupedTimeline:some View {',
'    private var freshTrackRail:some View {',
'''    private var freshGroupedTimeline:some View {
        GeometryReader{geo in
            ScrollView(.vertical,showsIndicators:false){
                HStack(spacing:0){
                    freshTrackRail
                        .frame(width:120,height:freshTimelineContentHeight,alignment:.top)
                    freshTimelineRows(width:max(220,geo.size.width-120))
                        .frame(width:max(220,geo.size.width-120),height:freshTimelineContentHeight,alignment:.top)
                }
            }
            .scrollDisabled(model.isMovingTimelineItem)
            .background(Color(red:0.135,green:0.135,blue:0.135))
        }
    }''')

block(
'    private var freshTrackRail:some View {',
'    private func freshGroupHeader(title:String,icon:String,expanded:Bool,accent:Color,mute:@escaping()->Void,solo:@escaping()->Void,add:@escaping()->Void,toggle:@escaping()->Void)->some View {',
'''    private var freshTrackRail:some View {
        VStack(spacing:0){
            freshGroupHeader(title:"Video",icon:"photo.on.rectangle",expanded:videoGroupExpanded,accent:.blue,
                             mute:{freshToggleVideoMute()},solo:{},add:{v060AddVideoMedia()},toggle:{withAnimation(.snappy){videoGroupExpanded.toggle()}})
            if videoGroupExpanded {
                ForEach(0..<freshVideoLaneCount,id:\\.self){lane in freshVideoTrackHeader(lane)}
                if freshVideoLaneCount>0 { freshAddSubtrackRow(title:"Video",enabled:freshVideoLaneCount<10){freshCreateVideoSubtrack()} }
            }

            freshGroupHeader(title:"Audio",icon:"music.note",expanded:audioGroupExpanded,accent:.green,
                             mute:{},solo:{},add:{v060AddAudio()},toggle:{withAnimation(.snappy){audioGroupExpanded.toggle()}})
            if audioGroupExpanded {
                ForEach(0..<freshAudioLaneCount,id:\\.self){lane in freshSimpleTrackHeader(kind:"audio",lane:lane,title:audioTrackNames[lane] ?? "name",accent:freshColor(audioColorIndex[lane] ?? 0,base:.green))}
                if freshAudioLaneCount>0 { freshAddSubtrackRow(title:"Audio",enabled:freshAudioLaneCount<10){freshCreateAudioSubtrack()} }
            }

            freshGroupHeader(title:"Text",icon:"textformat",expanded:textGroupExpanded,accent:.orange,
                             mute:{},solo:{},add:{v060AddText()},toggle:{withAnimation(.snappy){textGroupExpanded.toggle()}})
            if textGroupExpanded {
                ForEach(0..<freshTextLaneCount,id:\\.self){lane in freshSimpleTrackHeader(kind:"text",lane:lane,title:textTrackNames[lane] ?? "name",accent:freshColor(textColorIndex[lane] ?? 0,base:.orange))}
                if freshTextLaneCount>0 { freshAddSubtrackRow(title:"Text",enabled:freshTextLaneCount<10){freshCreateTextSubtrack()} }
            }

            freshGroupHeader(title:"FX",icon:"textformat.alt",expanded:fxGroupExpanded,accent:.purple,
                             mute:{},solo:{},add:{v060AddFX()},toggle:{withAnimation(.snappy){fxGroupExpanded.toggle()}})
            if fxGroupExpanded {
                ForEach(0..<freshFXLaneCount,id:\\.self){lane in freshSimpleTrackHeader(kind:"fx",lane:lane,title:fxTrackNames[lane] ?? "name",accent:freshColor(fxColorIndex[lane] ?? 0,base:.purple))}
                if freshFXLaneCount>0 { freshAddSubtrackRow(title:"FX",enabled:freshFXLaneCount<10){freshCreateFXSubtrack()} }
            }
        }
        .background(Color(red:0.10,green:0.10,blue:0.10))
        .overlay(alignment:.trailing){Rectangle().fill(Color.black.opacity(0.55)).frame(width:0.8)}
    }''')

block(
'    private func freshGroupHeader(title:String,icon:String,expanded:Bool,accent:Color,mute:@escaping()->Void,solo:@escaping()->Void,add:@escaping()->Void,toggle:@escaping()->Void)->some View {',
'    private func freshTinyButton(_ text:String,action:@escaping()->Void)->some View {',
'''    private func freshGroupHeader(title:String,icon:String,expanded:Bool,accent:Color,mute:@escaping()->Void,solo:@escaping()->Void,add:@escaping()->Void,toggle:@escaping()->Void)->some View {
        ZStack(alignment:.bottomTrailing){
            HStack(spacing:6){
                Image(systemName:icon)
                    .font(.system(size:title=="FX" ? 19:18,weight:.regular))
                    .foregroundStyle(.white)
                    .frame(width:25)
                Spacer(minLength:0)
                freshTinyButton("M",action:mute)
                freshTinyButton("S",action:solo)
                Button(action:add){
                    Image(systemName:"plus")
                        .font(.system(size:11,weight:.bold))
                        .foregroundStyle(.black)
                        .frame(width:22,height:22)
                        .background(Color.white.opacity(0.94),in:Circle())
                }.buttonStyle(.plain)
            }
            .padding(.horizontal,9)
            .frame(height:48)

            Button(action:toggle){
                Image(systemName:"triangle.fill")
                    .font(.system(size:8,weight:.bold))
                    .foregroundStyle(Color.white.opacity(0.92))
                    .rotationEffect(.degrees(expanded ? 180:0))
                    .frame(width:22,height:18)
            }
            .buttonStyle(.plain)
            .offset(x:-2,y:8)
        }
        .frame(height:48)
        .background(Color(red:0.09,green:0.09,blue:0.09))
        .overlay(alignment:.bottom){Rectangle().fill(Color.black.opacity(0.42)).frame(height:0.6)}
        .accessibilityLabel(title)
    }''')

block(
'    private func freshTinyButton(_ text:String,action:@escaping()->Void)->some View {',
'    private func freshVideoTrackHeader(_ lane:Int)->some View {',
'''    private func freshTinyButton(_ text:String,action:@escaping()->Void)->some View {
        Button(action:action){
            Text(text)
                .font(.system(size:9,weight:.bold))
                .foregroundStyle(.black)
                .frame(width:22,height:22)
                .background(Color.white.opacity(0.94),in:Circle())
        }.buttonStyle(.plain)
    }''')

block(
'    private func freshVideoTrackHeader(_ lane:Int)->some View {',
'    private func freshSimpleTrackHeader(kind:String,lane:Int,title:String,accent:Color)->some View {',
'''    private func freshVideoTrackHeader(_ lane:Int)->some View {
        let raw=trackNames[lane] ?? ""
        let automatic = raw.count>1 && raw.first=="V" && Int(raw.dropFirst()) != nil
        let shown = raw.isEmpty || automatic ? "name" : raw
        return HStack(spacing:6){
            Button{v060CycleTrackColor(lane)}label:{
                RoundedRectangle(cornerRadius:1.5).fill(v060TrackColor(lane)).frame(width:15,height:38)
            }.buttonStyle(.plain)
            VStack(alignment:.leading,spacing:5){
                Button{
                    freshRenameKind="video";renamingLane=lane;renameTrackText=shown;showRenameTrack=true
                }label:{
                    Text(shown).font(.system(size:10,weight:.medium)).foregroundStyle(.white).lineLimit(1).frame(maxWidth:.infinity,alignment:.leading)
                }.buttonStyle(.plain)
                HStack(spacing:5){
                    Button{inspector = .filters}label:{Text("Fx").font(.system(size:8,weight:.bold)).foregroundStyle(.black).frame(width:22,height:22).background(Color.white.opacity(0.94),in:Circle())}.buttonStyle(.plain)
                    freshTinyButton("M"){model.toggleTrackMute(lane)}
                    freshTinyButton("S"){model.toggleTrackBypass(lane)}
                }
            }
        }
        .padding(.horizontal,8)
        .frame(height:56)
        .background(Color(red:0.105,green:0.105,blue:0.105))
        .overlay(alignment:.bottom){
            VStack(spacing:2){Capsule().fill(Color.white.opacity(0.55)).frame(width:18,height:1);Capsule().fill(Color.white.opacity(0.55)).frame(width:18,height:1)}
                .offset(y:2)
        }
    }''')

block(
'    private func freshSimpleTrackHeader(kind:String,lane:Int,title:String,accent:Color)->some View {',
'    private func freshAddSubtrackRow(title:String,enabled:Bool,action:@escaping()->Void)->some View {',
'''    private func freshSimpleTrackHeader(kind:String,lane:Int,title:String,accent:Color)->some View {
        HStack(spacing:6){
            Button{freshCycleColor(kind:kind,lane:lane)}label:{RoundedRectangle(cornerRadius:1.5).fill(accent).frame(width:15,height:38)}.buttonStyle(.plain)
            VStack(alignment:.leading,spacing:5){
                Button{freshBeginRename(kind:kind,lane:lane,title:title)}label:{
                    Text(title).font(.system(size:10,weight:.medium)).foregroundStyle(.white).lineLimit(1).frame(maxWidth:.infinity,alignment:.leading)
                }.buttonStyle(.plain)
                HStack(spacing:5){
                    if kind=="fx" { Text("Fx").font(.system(size:8,weight:.bold)).foregroundStyle(.black).frame(width:22,height:22).background(Color.white.opacity(0.94),in:Circle()) }
                    freshTinyButton("M"){}
                    freshTinyButton("S"){}
                }
            }
        }
        .padding(.horizontal,8)
        .frame(height:56)
        .background(Color(red:0.105,green:0.105,blue:0.105))
        .overlay(alignment:.bottom){
            VStack(spacing:2){Capsule().fill(Color.white.opacity(0.55)).frame(width:18,height:1);Capsule().fill(Color.white.opacity(0.55)).frame(width:18,height:1)}
                .offset(y:2)
        }
    }''')

block(
'    private func freshAddSubtrackRow(title:String,enabled:Bool,action:@escaping()->Void)->some View {',
'    private func freshTimelineRows(width:CGFloat)->some View {',
'''    private func freshAddSubtrackRow(title:String,enabled:Bool,action:@escaping()->Void)->some View {
        Button(action:action){
            Image(systemName:"plus")
                .font(.system(size:11,weight:.bold))
                .foregroundStyle(enabled ? Color.white:Color.white.opacity(0.25))
                .frame(maxWidth:.infinity,maxHeight:.infinity)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .frame(height:26)
        .background(Color(red:0.105,green:0.105,blue:0.105))
        .accessibilityLabel("Добавить поддорожку \\(title)")
    }''')

block(
'    private func freshTimelineRows(width:CGFloat)->some View {',
'    private func freshMainSummaryRow(kind:String,accent:Color,width:CGFloat)->some View {',
'''    private func freshTimelineRows(width:CGFloat)->some View {
        ZStack(alignment:.topLeading){
            VStack(spacing:0){
                freshMainSummaryRow(kind:"video",accent:.blue,width:width)
                if videoGroupExpanded {
                    ForEach(0..<freshVideoLaneCount,id:\\.self){lane in freshVideoTimelineRow(lane:lane,width:width)}
                    if freshVideoLaneCount>0 { Color.clear.frame(height:26) }
                }
                freshMainSummaryRow(kind:"audio",accent:.green,width:width)
                if audioGroupExpanded {
                    ForEach(0..<freshAudioLaneCount,id:\\.self){lane in freshAudioTimelineRow(lane:lane,width:width)}
                    if freshAudioLaneCount>0 { Color.clear.frame(height:26) }
                }
                freshMainSummaryRow(kind:"text",accent:.orange,width:width)
                if textGroupExpanded {
                    ForEach(0..<freshTextLaneCount,id:\\.self){lane in freshTextTimelineRow(lane:lane,width:width)}
                    if freshTextLaneCount>0 { Color.clear.frame(height:26) }
                }
                freshMainSummaryRow(kind:"fx",accent:.purple,width:width)
                if fxGroupExpanded {
                    ForEach(0..<freshFXLaneCount,id:\\.self){lane in freshFXTimelineRow(lane:lane,width:width)}
                    if freshFXLaneCount>0 { Color.clear.frame(height:26) }
                }
            }
            Rectangle()
                .fill(Color.white.opacity(0.72))
                .frame(width:1.2,height:freshTimelineContentHeight)
                .position(x:width/2,y:freshTimelineContentHeight/2)
                .allowsHitTesting(false)
                .zIndex(300)
        }
        .background(Color(red:0.135,green:0.135,blue:0.135))
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
'    private func freshMainSummaryRow(kind:String,accent:Color,width:CGFloat)->some View {',
'    private func freshVideoTimelineRow(lane:Int,width:CGFloat)->some View {',
'''    private func freshMainSummaryRow(kind:String,accent:Color,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom
        let center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(red:0.135,green:0.135,blue:0.135))
            Rectangle().fill(Color.black.opacity(0.28)).frame(height:0.6).offset(y:47.4)

            if kind=="video" && model.projectDuration>0.02 {
                let w=max(28,CGFloat(model.projectDuration*pps))
                let x=center+CGFloat((0-model.projectTime)*pps)+w/2
                HStack(spacing:5){
                    Image(systemName:"film").font(.system(size:10,weight:.semibold))
                    Text("Video").font(.system(size:9,weight:.semibold)).lineLimit(1)
                }
                .foregroundStyle(.white)
                .padding(.horizontal,7)
                .frame(width:w,height:30,alignment:.leading)
                .background(Color.white.opacity(0.15),in:RoundedRectangle(cornerRadius:2))
                .position(x:x,y:24)
            }

            if kind=="audio" {
                ForEach(model.audioClips){a in
                    let w=max(42,CGFloat(a.duration*pps))
                    let x=center+CGFloat((a.start-model.projectTime)*pps)+w/2
                    FreshAudioClipCardV065(name:a.name,width:w,selected:false,onTap:{},onMove:{_ in})
                        .position(x:x,y:24)
                }
            }

            if kind=="text" && !model.overlayText.isEmpty {
                let w=max(72,CGFloat(max(1,model.projectDuration)*pps))
                let x=center+CGFloat((0-model.projectTime)*pps)+w/2
                HStack(spacing:4){Image(systemName:"textformat");Text(model.overlayText).lineLimit(1)}
                    .font(.system(size:9,weight:.medium)).foregroundStyle(.white)
                    .padding(.horizontal,7).frame(width:w,height:30,alignment:.leading)
                    .background(Color.white.opacity(0.20),in:RoundedRectangle(cornerRadius:2))
                    .position(x:x,y:24)
            }

            if kind=="fx" {
                ForEach(model.speedFX){fx in
                    let w=max(48,CGFloat(fx.duration*pps))
                    let x=center+CGFloat((fx.start-model.projectTime)*pps)+w/2
                    HStack(spacing:4){Text("Fx").font(.system(size:9,weight:.bold));Text(fx.name).font(.system(size:8)).lineLimit(1)}
                        .foregroundStyle(.white)
                        .padding(.horizontal,7).frame(width:w,height:30,alignment:.leading)
                        .background(Color.white.opacity(0.18),in:RoundedRectangle(cornerRadius:2))
                        .position(x:x,y:24)
                }
            }
        }
        .frame(height:48)
        .clipped()
    }''')

# Fixed dark subtrack canvases and reference row heights.
s=s.replace('Rectangle().fill(Color(uiColor:.systemBackground))\n            Rectangle().fill(Color.primary.opacity(0.045)).frame(height:0.5).offset(y:45.5)',
            'Rectangle().fill(Color(red:0.135,green:0.135,blue:0.135))\n            Rectangle().fill(Color.black.opacity(0.28)).frame(height:0.6).offset(y:55.4)',2)
s=s.replace('}.frame(height:46).clipped()','}.frame(height:56).clipped()',2)
s=s.replace('.position(x:x,y:23)','.position(x:x,y:28)',2)

block(
'    private func freshTextTimelineRow(lane:Int,width:CGFloat)->some View {',
'    private func freshFXTimelineRow(lane:Int,width:CGFloat)->some View {',
'''    private func freshTextTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(red:0.135,green:0.135,blue:0.135))
            if lane==0 && !model.overlayText.isEmpty {
                let w=max(70,CGFloat(max(1,model.projectDuration)*pps))
                let x=center+CGFloat((0-model.projectTime)*pps)+w/2
                Button{inspector = .text}label:{
                    HStack(spacing:5){Image(systemName:"textformat");Text(model.overlayText).lineLimit(1)}
                        .font(.system(size:9,weight:.semibold)).foregroundStyle(.white)
                        .padding(.horizontal,7).frame(width:w,height:34,alignment:.leading)
                        .background(Color(red:0.55,green:0.52,blue:0.72),in:RoundedRectangle(cornerRadius:2))
                }.buttonStyle(.plain).position(x:x,y:28)
            }
        }.frame(height:56).clipped()
    }''')

block(
'    private func freshFXTimelineRow(lane:Int,width:CGFloat)->some View {',
'    private var freshBottomToolbar:some View {',
'''    private func freshFXTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(red:0.135,green:0.135,blue:0.135))
            if lane==0 {
                ForEach(model.speedFX){fx in
                    let w=max(52,CGFloat(fx.duration*pps))
                    let x=center+CGFloat((fx.start-model.projectTime)*pps)+w/2
                    Button{curveTarget = .global(fx.id)}label:{
                        HStack(spacing:4){Text("Fx").font(.system(size:9,weight:.bold));Text(fx.name).lineLimit(1)}
                            .font(.system(size:9,weight:.semibold)).foregroundStyle(.white)
                            .padding(.horizontal,7).frame(width:w,height:34,alignment:.leading)
                            .background(Color(red:0.55,green:0.52,blue:0.72),in:RoundedRectangle(cornerRadius:2))
                    }.buttonStyle(.plain).position(x:x,y:28)
                }
            }
        }.frame(height:56).clipped()
    }''')

block(
'    private var freshBottomToolbar:some View {',
'    private func freshTool(_ icon:String,_ title:String,_ tool:InspectorTool)->some View {',
'''    private var freshBottomToolbar:some View {
        ZStack{
            Color(red:0.135,green:0.135,blue:0.135)
            ScrollView(.horizontal,showsIndicators:false){
                HStack(spacing:8){
                    freshTool("scissors","Обрезка",.trim)
                    freshTool("speedometer","Скорость",.speed)
                    freshTool("waveform.path.ecg.rectangle","Speed FX",.speed)
                    freshTool("waveform","Аудио",.audio)
                    freshTool("textformat","Текст",.text)
                    freshTool("camera.filters","Фильтры",.filters)
                    freshTool("slider.horizontal.3","Настройки",.adjust)
                }
                .padding(.horizontal,10)
                .padding(.vertical,8)
            }
            .background(Color.white,in:RoundedRectangle(cornerRadius:0))
            .padding(.horizontal,10)
            .padding(.vertical,8)
        }
        .frame(height:82)
        .overlay(alignment:.top){Rectangle().fill(Color.black.opacity(0.35)).frame(height:0.6)}
    }''')

block(
'    private func freshTool(_ icon:String,_ title:String,_ tool:InspectorTool)->some View {',
'    private func freshCreateVideoSubtrack(){',
'''    private func freshTool(_ icon:String,_ title:String,_ tool:InspectorTool)->some View {
        Button{inspector=tool}label:{
            Image(systemName:icon)
                .font(.system(size:20,weight:.regular))
                .foregroundStyle(.black)
                .frame(width:48,height:48)
                .background(Color.white,in:Circle())
                .overlay(Circle().stroke(Color.black.opacity(0.09),lineWidth:0.7))
                .shadow(color:.black.opacity(0.18),radius:4,y:2)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
    }''')

p.write_text(s)
print('Applied VeloCut v0.6.2 reference-matched editor UI')
