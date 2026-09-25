from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# VeloCut v0.6.1 — completely new editor presentation.
# Keep the proven media/composition engine, but replace the workspace visually.

# -----------------------------------------------------------------------------
# State used only by the new presentation.
# -----------------------------------------------------------------------------
state_anchor='@State private var trackColorIndex: [Int:Int] = [:]'
if state_anchor not in s:
    raise RuntimeError('v0.6.0 grouped state anchor missing')
state_extra='''
    @State private var freshZoomStart: Double?
    @State private var freshRenameKind = "video"
    @State private var audioTrackNames: [Int:String] = [:]
    @State private var textTrackNames: [Int:String] = [:]
    @State private var fxTrackNames: [Int:String] = [:]
    @State private var audioColorIndex: [Int:Int] = [:]
    @State private var textColorIndex: [Int:Int] = [:]
    @State private var fxColorIndex: [Int:Int] = [:]
'''
s=s.replace(state_anchor,state_anchor+state_extra,1)

# -----------------------------------------------------------------------------
# Improve grouped import semantics: first + auto-creates a subtrack; later +
# targets the last created subtrack. The small + Track control creates empty
# subtracks up to ten.
# -----------------------------------------------------------------------------
old_audio='''    private func v060AddAudio() {
        if audioSubtrackCount == 0 { audioSubtrackCount=1 }
        audioGroupExpanded=true
        showAudioSourceMenu=true
    }'''
new_audio='''    private func v060AddAudio() {
        if audioSubtrackCount == 0 { audioSubtrackCount=1 }
        let lane=max(0,audioSubtrackCount-1)
        while model.trackCount <= lane && model.trackCount < 10 { model.addTrack() }
        audioGroupExpanded=true
        showAudioSourceMenu=true
    }'''
if old_audio in s:
    s=s.replace(old_audio,new_audio,1)

# Main audio dialog should import into the current last audio subtrack.
s=s.replace('''                pendingAudioLane=0
                model.isAudioImporting=true''','''                pendingAudioLane=max(0,audioSubtrackCount-1)
                model.isAudioImporting=true''',1)
s=s.replace('''                pendingExtractLane=0
                showTrackExtractPicker=true''','''                pendingExtractLane=max(0,audioSubtrackCount-1)
                showTrackExtractPicker=true''',1)

# -----------------------------------------------------------------------------
# Generic rename alert: extend the existing keyboard rename workflow to all
# four groups without adding another competing SwiftUI alert.
# -----------------------------------------------------------------------------
old_save='''            Button("Сохранить"){
                if let lane=renamingLane{
                    let clean=renameTrackText.trimmingCharacters(in:.whitespacesAndNewlines)
                    trackNames[lane]=clean.isEmpty ? "V\\(lane+1)" : String(clean.prefix(18))
                }
                renamingLane=nil
            }'''
new_save='''            Button("Сохранить"){
                if let lane=renamingLane{
                    let clean=renameTrackText.trimmingCharacters(in:.whitespacesAndNewlines)
                    let fallback:String
                    switch freshRenameKind {
                    case "audio": fallback="Audio \\(lane+1)"
                    case "text": fallback="Text \\(lane+1)"
                    case "fx": fallback="FX \\(lane+1)"
                    default: fallback="Video \\(lane+1)"
                    }
                    let value=clean.isEmpty ? fallback : String(clean.prefix(18))
                    switch freshRenameKind {
                    case "audio": audioTrackNames[lane]=value
                    case "text": textTrackNames[lane]=value
                    case "fx": fxTrackNames[lane]=value
                    default: trackNames[lane]=value
                    }
                }
                renamingLane=nil
            }'''
if old_save in s:
    s=s.replace(old_save,new_save,1)

# -----------------------------------------------------------------------------
# Replace adaptiveWorkspace completely. This is the important part: the old
# editor chrome, old timeline card, old rail and old toolbar are no longer used.
# -----------------------------------------------------------------------------
pat=re.compile(r'    @ViewBuilder private func adaptiveWorkspace\(_ root: GeometryProxy\)->some View \{.*?\n    \}\n\n    private var workspaceHandle:',re.S)
new_workspace='''    @ViewBuilder private func adaptiveWorkspace(_ root: GeometryProxy)->some View {
        VStack(spacing:0){
            freshPreviewArea(root)
                .frame(height:max(250,min(390,root.size.height*0.39)))
            freshTimelineHeader
            freshGroupedTimeline
                .frame(maxHeight:.infinity)
            freshBottomToolbar
        }
        .background(Color(uiColor:.systemBackground))
    }

    private var workspaceHandle:'''
s,n=pat.subn(new_workspace,s,count=1)
if n!=1:
    raise RuntimeError('adaptiveWorkspace replacement failed')

# -----------------------------------------------------------------------------
# Insert the entire new UI inside EditorView, before the legacy topBar. Legacy
# views remain compiled but unused so the editing engine stays stable.
# -----------------------------------------------------------------------------
insert_anchor='    private var topBar:some View'
if insert_anchor not in s:
    raise RuntimeError('topBar insertion anchor missing')

fresh=r'''
    // MARK: - VeloCut fresh workspace v0.6.1

    private func freshPreviewArea(_ root:GeometryProxy)->some View {
        ZStack{
            Color.black
            VStack(spacing:0){
                HStack{
                    Text("VeloCut")
                        .font(.system(size:22,weight:.black,design:.rounded))
                        .foregroundStyle(.white)
                    Spacer()
                    Button{inspector = .export}label:{
                        Text("EXPORT")
                            .font(.system(size:12,weight:.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal,15)
                            .frame(height:32)
                            .background(Color.white.opacity(model.clips.isEmpty ? 0.12:0.20),in:Capsule())
                    }
                    .buttonStyle(.plain)
                    .disabled(model.clips.isEmpty)
                }
                .padding(.horizontal,17)
                .frame(height:46)

                ZStack{
                    Rectangle().fill(Color.black)
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
                                Circle().fill(Color.white.opacity(0.12)).frame(width:76,height:76)
                                Circle().stroke(Color.white.opacity(0.55),lineWidth:1).frame(width:76,height:76)
                                Image(systemName:"plus")
                                    .font(.system(size:34,weight:.light))
                                    .foregroundStyle(.white)
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Добавить видео или фото")
                    }
                }
                .frame(maxWidth:.infinity,maxHeight:.infinity)

                HStack{
                    Spacer()
                    Button{model.playPause()}label:{
                        Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                            .font(.system(size:20,weight:.semibold))
                            .foregroundStyle(.white)
                            .frame(width:44,height:36)
                    }
                    .buttonStyle(.plain)
                    .disabled(model.clips.isEmpty)
                    Spacer()
                    HStack(spacing:18){
                        Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward")}.disabled(!model.canUndo)
                        Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward")}.disabled(!model.canRedo)
                    }
                    .font(.system(size:17,weight:.medium))
                    .foregroundStyle(.white)
                }
                .padding(.horizontal,18)
                .frame(height:44)
            }
        }
    }

    private var freshTimelineHeader:some View {
        HStack(spacing:0){
            Color(uiColor:.secondarySystemBackground)
                .frame(width:146,height:30)
                .overlay(alignment:.leading){
                    Text("TRACKS")
                        .font(.system(size:9,weight:.bold))
                        .foregroundStyle(.secondary)
                        .padding(.leading,12)
                }
            ZStack{
                Color(uiColor:.systemBackground)
                TimelineRulerV4(projectTime:model.projectTime,duration:model.projectDuration,pps:40*model.timelineZoom)
                    .frame(height:24)
                HStack{
                    Spacer()
                    Button{model.timelineZoom=max(0.55,model.timelineZoom-0.18)}label:{Image(systemName:"minus.magnifyingglass")}
                    Button{model.timelineZoom=min(3.2,model.timelineZoom+0.18)}label:{Image(systemName:"plus.magnifyingglass")}
                }
                .font(.system(size:12))
                .padding(.trailing,8)
                .foregroundStyle(.secondary)
            }
            .frame(height:30)
        }
        .overlay(alignment:.bottom){Divider()}
    }

    private var freshVideoLaneCount:Int {
        min(10,max(videoSubtrackCount,(model.clips.map{$0.track}.max() ?? -1)+1))
    }
    private var freshAudioLaneCount:Int {
        min(10,max(audioSubtrackCount,(model.audioClips.map{$0.track}.max() ?? -1)+1))
    }
    private var freshTextLaneCount:Int { min(10,max(textSubtrackCount,model.overlayText.isEmpty ? 0:1)) }
    private var freshFXLaneCount:Int { min(10,max(fxSubtrackCount,model.speedFX.isEmpty ? 0:1)) }

    private var freshTimelineContentHeight:CGFloat {
        let main=CGFloat(4*42)
        let v=videoGroupExpanded ? CGFloat(freshVideoLaneCount*46 + 30):0
        let a=audioGroupExpanded ? CGFloat(freshAudioLaneCount*46 + 30):0
        let t=textGroupExpanded ? CGFloat(freshTextLaneCount*46 + 30):0
        let f=fxGroupExpanded ? CGFloat(freshFXLaneCount*46 + 30):0
        return max(260,main+v+a+t+f)
    }

    private var freshGroupedTimeline:some View {
        GeometryReader{geo in
            ScrollView(.vertical,showsIndicators:false){
                HStack(spacing:0){
                    freshTrackRail
                        .frame(width:146,height:freshTimelineContentHeight,alignment:.top)
                    freshTimelineRows(width:max(220,geo.size.width-146))
                        .frame(width:max(220,geo.size.width-146),height:freshTimelineContentHeight,alignment:.top)
                }
            }
            .background(Color(uiColor:.systemBackground))
        }
    }

    private var freshTrackRail:some View {
        VStack(spacing:0){
            freshGroupHeader(title:"Video",icon:"photo.on.rectangle",expanded:videoGroupExpanded,accent:.blue,
                             mute:{freshToggleVideoMute()},solo:{},add:{v060AddVideoMedia()},toggle:{withAnimation(.snappy){videoGroupExpanded.toggle()}})
            if videoGroupExpanded {
                ForEach(0..<freshVideoLaneCount,id:\.self){lane in freshVideoTrackHeader(lane)}
                freshAddSubtrackRow(title:"+ Video Track",enabled:freshVideoLaneCount<10){freshCreateVideoSubtrack()}
            }

            freshGroupHeader(title:"Audio",icon:"music.note",expanded:audioGroupExpanded,accent:.green,
                             mute:{},solo:{},add:{v060AddAudio()},toggle:{withAnimation(.snappy){audioGroupExpanded.toggle()}})
            if audioGroupExpanded {
                ForEach(0..<freshAudioLaneCount,id:\.self){lane in freshSimpleTrackHeader(kind:"audio",lane:lane,title:audioTrackNames[lane] ?? "Audio \\(lane+1)",accent:freshColor(audioColorIndex[lane] ?? 0,base:.green))}
                freshAddSubtrackRow(title:"+ Audio Track",enabled:freshAudioLaneCount<10){freshCreateAudioSubtrack()}
            }

            freshGroupHeader(title:"Text",icon:"textformat",expanded:textGroupExpanded,accent:.orange,
                             mute:{},solo:{},add:{v060AddText()},toggle:{withAnimation(.snappy){textGroupExpanded.toggle()}})
            if textGroupExpanded {
                ForEach(0..<freshTextLaneCount,id:\.self){lane in freshSimpleTrackHeader(kind:"text",lane:lane,title:textTrackNames[lane] ?? "Text \\(lane+1)",accent:freshColor(textColorIndex[lane] ?? 0,base:.orange))}
                freshAddSubtrackRow(title:"+ Text Track",enabled:freshTextLaneCount<10){freshCreateTextSubtrack()}
            }

            freshGroupHeader(title:"FX",icon:"sparkles",expanded:fxGroupExpanded,accent:.purple,
                             mute:{},solo:{},add:{v060AddFX()},toggle:{withAnimation(.snappy){fxGroupExpanded.toggle()}})
            if fxGroupExpanded {
                ForEach(0..<freshFXLaneCount,id:\.self){lane in freshSimpleTrackHeader(kind:"fx",lane:lane,title:fxTrackNames[lane] ?? "FX \\(lane+1)",accent:freshColor(fxColorIndex[lane] ?? 0,base:.purple))}
                freshAddSubtrackRow(title:"+ FX Track",enabled:freshFXLaneCount<10){freshCreateFXSubtrack()}
            }
        }
        .background(Color(uiColor:.secondarySystemBackground))
        .overlay(alignment:.trailing){Rectangle().fill(Color.primary.opacity(0.08)).frame(width:0.5)}
    }

    private func freshGroupHeader(title:String,icon:String,expanded:Bool,accent:Color,mute:@escaping()->Void,solo:@escaping()->Void,add:@escaping()->Void,toggle:@escaping()->Void)->some View {
        HStack(spacing:5){
            Button(action:toggle){
                Image(systemName:"triangle.fill")
                    .font(.system(size:7,weight:.bold))
                    .rotationEffect(.degrees(expanded ? 180:90))
                    .frame(width:13,height:22)
            }
            .buttonStyle(.plain)
            Image(systemName:icon).font(.system(size:12,weight:.medium)).frame(width:17)
            Text(title).font(.system(size:11,weight:.bold)).lineLimit(1)
            Spacer(minLength:1)
            freshTinyButton("M",action:mute)
            freshTinyButton("S",action:solo)
            Button(action:add){
                Image(systemName:"plus")
                    .font(.system(size:10,weight:.bold))
                    .frame(width:21,height:21)
                    .background(accent.opacity(0.15),in:RoundedRectangle(cornerRadius:5))
            }.buttonStyle(.plain)
        }
        .padding(.horizontal,7)
        .frame(height:42)
        .background(Color(uiColor:.tertiarySystemBackground))
    }

    private func freshTinyButton(_ text:String,action:@escaping()->Void)->some View {
        Button(action:action){
            Text(text).font(.system(size:8,weight:.bold))
                .frame(width:20,height:20)
                .background(Color.primary.opacity(0.07),in:RoundedRectangle(cornerRadius:5))
        }.buttonStyle(.plain)
    }

    private func freshVideoTrackHeader(_ lane:Int)->some View {
        HStack(spacing:5){
            Button{v060CycleTrackColor(lane)}label:{
                RoundedRectangle(cornerRadius:3).fill(v060TrackColor(lane)).frame(width:12,height:25)
            }.buttonStyle(.plain)
            Button{
                freshRenameKind="video";renamingLane=lane;renameTrackText=trackNames[lane] ?? "Video \\(lane+1)";showRenameTrack=true
            }label:{
                Text(trackNames[lane] ?? "Video \\(lane+1)").font(.system(size:9,weight:.semibold)).lineLimit(1).frame(maxWidth:.infinity,alignment:.leading)
            }.buttonStyle(.plain)
            Button{inspector = .filters}label:{Text("Fx").font(.system(size:8,weight:.bold)).frame(width:20,height:20).background(Color.primary.opacity(0.06),in:RoundedRectangle(cornerRadius:4))}.buttonStyle(.plain)
            freshTinyButton("M"){model.toggleTrackMute(lane)}
            freshTinyButton("S"){model.toggleTrackBypass(lane)}
        }
        .padding(.horizontal,8)
        .frame(height:46)
        .background(Color(uiColor:.secondarySystemBackground))
    }

    private func freshSimpleTrackHeader(kind:String,lane:Int,title:String,accent:Color)->some View {
        HStack(spacing:5){
            Button{freshCycleColor(kind:kind,lane:lane)}label:{RoundedRectangle(cornerRadius:3).fill(accent).frame(width:12,height:25)}.buttonStyle(.plain)
            Button{freshBeginRename(kind:kind,lane:lane,title:title)}label:{Text(title).font(.system(size:9,weight:.semibold)).lineLimit(1).frame(maxWidth:.infinity,alignment:.leading)}.buttonStyle(.plain)
            freshTinyButton("M"){}
            freshTinyButton("S"){}
        }
        .padding(.horizontal,8)
        .frame(height:46)
        .background(Color(uiColor:.secondarySystemBackground))
    }

    private func freshAddSubtrackRow(title:String,enabled:Bool,action:@escaping()->Void)->some View {
        Button(action:action){
            HStack(spacing:5){Image(systemName:"plus").font(.system(size:9,weight:.bold));Text(title).font(.system(size:9,weight:.medium));Spacer()}
                .foregroundStyle(enabled ? Color.secondary:Color.secondary.opacity(0.35))
                .padding(.horizontal,12)
                .frame(height:30)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    private func freshTimelineRows(width:CGFloat)->some View {
        ZStack(alignment:.topLeading){
            VStack(spacing:0){
                freshMainSummaryRow(kind:"video",accent:.blue,width:width)
                if videoGroupExpanded {
                    ForEach(0..<freshVideoLaneCount,id:\.self){lane in freshVideoTimelineRow(lane:lane,width:width)}
                    Color.clear.frame(height:30)
                }
                freshMainSummaryRow(kind:"audio",accent:.green,width:width)
                if audioGroupExpanded {
                    ForEach(0..<freshAudioLaneCount,id:\.self){lane in freshAudioTimelineRow(lane:lane,width:width)}
                    Color.clear.frame(height:30)
                }
                freshMainSummaryRow(kind:"text",accent:.orange,width:width)
                if textGroupExpanded {
                    ForEach(0..<freshTextLaneCount,id:\.self){lane in freshTextTimelineRow(lane:lane,width:width)}
                    Color.clear.frame(height:30)
                }
                freshMainSummaryRow(kind:"fx",accent:.purple,width:width)
                if fxGroupExpanded {
                    ForEach(0..<freshFXLaneCount,id:\.self){lane in freshFXTimelineRow(lane:lane,width:width)}
                    Color.clear.frame(height:30)
                }
            }
            Rectangle()
                .fill(Color.red.opacity(0.92))
                .frame(width:1.5,height:freshTimelineContentHeight)
                .position(x:width/2,y:freshTimelineContentHeight/2)
                .allowsHitTesting(false)
                .zIndex(300)
        }
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
    }

    private func freshMainSummaryRow(kind:String,accent:Color,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom
        let center=width/2
        let duration:Double = {
            switch kind {
            case "audio": return model.audioClips.map{$0.end}.max() ?? 0
            case "text": return model.overlayText.isEmpty ? 0:model.projectDuration
            case "fx": return model.speedFX.map{$0.start+$0.duration}.max() ?? 0
            default: return model.projectDuration
            }
        }()
        return ZStack(alignment:.leading){
            Rectangle().fill(Color(uiColor:.systemBackground))
            Rectangle().fill(Color.primary.opacity(0.035)).frame(height:1).offset(y:20)
            if duration>0.02 {
                let x=center+CGFloat((0-model.projectTime)*pps)
                let w=max(20,CGFloat(duration*pps))
                RoundedRectangle(cornerRadius:5).fill(accent.opacity(0.16)).frame(width:w,height:20).offset(x:x,y:11)
            }
        }
        .frame(height:42)
    }

    private func freshVideoTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(uiColor:.systemBackground))
            Rectangle().fill(Color.primary.opacity(0.045)).frame(height:0.5).offset(y:45.5)
            ForEach(Array(model.layouts.enumerated()).filter{$0.element.clip.track==lane},id:\.element.id){index,l in
                let w=max(48,CGFloat(l.duration*pps))
                let x=center+CGFloat((l.start-model.projectTime)*pps)+w/2
                FreshVideoClipCardV065(name:l.clip.name,width:w,color:v060TrackColor(lane),selected:model.selectedClipID==l.id,
                    onTap:{model.selectClip(l.id)},
                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{model.moveClip(l.id,translation:$0,pps:pps)})
                    .position(x:x,y:23)
            }
        }.frame(height:46).clipped()
    }

    private func freshAudioTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(uiColor:.systemBackground))
            Rectangle().fill(Color.primary.opacity(0.045)).frame(height:0.5).offset(y:45.5)
            ForEach(model.audioClips.filter{$0.track==lane}){a in
                let w=max(48,CGFloat(a.duration*pps))
                let x=center+CGFloat((a.start-model.projectTime)*pps)+w/2
                FreshAudioClipCardV065(name:a.name,width:w,selected:model.selectedAudioClipID==a.id,
                    onTap:{model.selectAudioClip(a.id)},
                    onMove:{model.moveAudioClip(a.id,translation:$0,pps:pps)})
                    .position(x:x,y:23)
            }
        }.frame(height:46).clipped()
    }

    private func freshTextTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(uiColor:.systemBackground))
            if lane==0 && !model.overlayText.isEmpty {
                let w=max(70,CGFloat(max(1,model.projectDuration)*pps))
                let x=center+CGFloat((0-model.projectTime)*pps)+w/2
                Button{inspector = .text}label:{
                    HStack(spacing:5){Image(systemName:"textformat");Text(model.overlayText).lineLimit(1)}
                        .font(.system(size:9,weight:.semibold)).foregroundStyle(.white)
                        .padding(.horizontal,7).frame(width:w,height:32,alignment:.leading)
                        .background(Color.orange,in:RoundedRectangle(cornerRadius:6))
                }.buttonStyle(.plain).position(x:x,y:23)
            }
        }.frame(height:46).clipped()
    }

    private func freshFXTimelineRow(lane:Int,width:CGFloat)->some View {
        let pps=40.0*model.timelineZoom,center=width/2
        return ZStack(alignment:.topLeading){
            Rectangle().fill(Color(uiColor:.systemBackground))
            if lane==0 {
                ForEach(model.speedFX){fx in
                    let w=max(52,CGFloat(fx.duration*pps))
                    let x=center+CGFloat((fx.start-model.projectTime)*pps)+w/2
                    Button{curveTarget = .global(fx.id)}label:{
                        HStack(spacing:4){Image(systemName:"sparkles");Text(fx.name).lineLimit(1)}
                            .font(.system(size:9,weight:.semibold)).foregroundStyle(.white)
                            .padding(.horizontal,7).frame(width:w,height:32,alignment:.leading)
                            .background(Color.purple,in:RoundedRectangle(cornerRadius:6))
                    }.buttonStyle(.plain).position(x:x,y:23)
                }
            }
        }.frame(height:46).clipped()
    }

    private var freshBottomToolbar:some View {
        ScrollView(.horizontal,showsIndicators:false){
            HStack(spacing:5){
                freshTool("scissors","Обрезка",.trim)
                freshTool("speedometer","Скорость",.speed)
                freshTool("waveform.path.ecg.rectangle","Speed FX",.speed)
                freshTool("waveform","Аудио",.audio)
                freshTool("textformat","Текст",.text)
                freshTool("camera.filters","Фильтры",.filters)
                freshTool("slider.horizontal.3","Настройки",.adjust)
            }
            .padding(.horizontal,10)
        }
        .frame(height:72)
        .background(Color(uiColor:.systemBackground))
        .overlay(alignment:.top){Divider()}
    }

    private func freshTool(_ icon:String,_ title:String,_ tool:InspectorTool)->some View {
        Button{inspector=tool}label:{
            VStack(spacing:4){
                Image(systemName:icon).font(.system(size:16,weight:.medium))
                Text(title).font(.system(size:8,weight:.medium)).lineLimit(1)
            }
            .foregroundStyle(Color.primary)
            .frame(width:66,height:54)
            .background(Color(uiColor:.secondarySystemBackground),in:RoundedRectangle(cornerRadius:17,style:.continuous))
        }.buttonStyle(.plain)
    }

    private func freshCreateVideoSubtrack(){
        guard freshVideoLaneCount<10 else{model.haptic(.error);return}
        videoSubtrackCount=freshVideoLaneCount+1
        while model.trackCount<videoSubtrackCount && model.trackCount<10{model.addTrack()}
        videoGroupExpanded=true
    }
    private func freshCreateAudioSubtrack(){
        guard freshAudioLaneCount<10 else{model.haptic(.error);return}
        audioSubtrackCount=freshAudioLaneCount+1
        while model.trackCount<audioSubtrackCount && model.trackCount<10{model.addTrack()}
        audioGroupExpanded=true
    }
    private func freshCreateTextSubtrack(){guard freshTextLaneCount<10 else{model.haptic(.error);return};textSubtrackCount=freshTextLaneCount+1;textGroupExpanded=true;model.haptic(.selection)}
    private func freshCreateFXSubtrack(){guard freshFXLaneCount<10 else{model.haptic(.error);return};fxSubtrackCount=freshFXLaneCount+1;fxGroupExpanded=true;model.haptic(.selection)}

    private func freshToggleVideoMute(){
        let lanes=Array(0..<freshVideoLaneCount)
        guard !lanes.isEmpty else{return}
        let allMuted=lanes.allSatisfy{model.mutedTracks.contains($0)}
        for lane in lanes { if allMuted { if model.mutedTracks.contains(lane){model.toggleTrackMute(lane)} } else { if !model.mutedTracks.contains(lane){model.toggleTrackMute(lane)} } }
    }

    private func freshBeginRename(kind:String,lane:Int,title:String){freshRenameKind=kind;renamingLane=lane;renameTrackText=title;showRenameTrack=true}

    private func freshColor(_ index:Int,base:Color)->Color {
        switch index%6 {case 1:return .blue;case 2:return .red;case 3:return .purple;case 4:return .green;case 5:return .orange;default:return base}
    }
    private func freshCycleColor(kind:String,lane:Int){
        switch kind {
        case "audio": audioColorIndex[lane]=((audioColorIndex[lane] ?? 0)+1)%6
        case "text": textColorIndex[lane]=((textColorIndex[lane] ?? 0)+1)%6
        case "fx": fxColorIndex[lane]=((fxColorIndex[lane] ?? 0)+1)%6
        default: break
        }
        model.haptic(.selection)
    }

'''
s=s.replace(insert_anchor,fresh+insert_anchor,1)

# -----------------------------------------------------------------------------
# Add truly new clip cards after EditorView. No old card is used by fresh UI.
# -----------------------------------------------------------------------------
card_anchor='struct TimelineRulerV4:View'
if card_anchor not in s:
    raise RuntimeError('TimelineRulerV4 anchor missing')
new_cards=r'''
struct FreshVideoClipCardV065:View{
    let name:String
    let width:CGFloat
    let color:Color
    let selected:Bool
    let onTap:()->Void
    let onMenu:()->Void
    let onMove:(CGSize)->Void
    @State private var drag:CGSize=.zero
    var body:some View{
        HStack(spacing:5){
            Image(systemName:"film").font(.system(size:10,weight:.semibold))
            Text(name).font(.system(size:9,weight:.semibold)).lineLimit(1)
            Spacer(minLength:0)
        }
        .foregroundStyle(.white)
        .padding(.horizontal,7)
        .frame(width:width,height:34)
        .background(color.opacity(color==Color.primary.opacity(0.10) ? 0.55:0.88),in:RoundedRectangle(cornerRadius:6))
        .overlay(RoundedRectangle(cornerRadius:6).stroke(selected ? Color.white:Color.clear,lineWidth:2))
        .shadow(color:selected ? Color.black.opacity(0.18):.clear,radius:3)
        .offset(drag)
        .onTapGesture{onTap()}
        .highPriorityGesture(
            LongPressGesture(minimumDuration:0.30).sequenced(before:DragGesture(minimumDistance:0))
                .onChanged{v in if case .second(true,let d?)=v{drag=d.translation}}
                .onEnded{v in
                    defer{drag=.zero}
                    if case .second(true,let d?)=v{
                        if hypot(d.translation.width,d.translation.height)<8{onMenu()}else{onMove(d.translation)}
                    }else{onMenu()}
                }
        )
    }
}

struct FreshAudioClipCardV065:View{
    let name:String
    let width:CGFloat
    let selected:Bool
    let onTap:()->Void
    let onMove:(CGSize)->Void
    @State private var drag:CGSize=.zero
    var body:some View{
        ZStack(alignment:.leading){
            RoundedRectangle(cornerRadius:6).fill(Color.green.opacity(0.82))
            HStack(spacing:3){
                Image(systemName:"waveform").font(.system(size:10,weight:.bold))
                Text(name).font(.system(size:9,weight:.semibold)).lineLimit(1)
            }.foregroundStyle(.white).padding(.horizontal,7)
        }
        .frame(width:width,height:34)
        .overlay(RoundedRectangle(cornerRadius:6).stroke(selected ? Color.white:Color.clear,lineWidth:2))
        .offset(drag)
        .onTapGesture{onTap()}
        .highPriorityGesture(
            LongPressGesture(minimumDuration:0.30).sequenced(before:DragGesture(minimumDistance:0))
                .onChanged{v in if case .second(true,let d?)=v{drag=d.translation}}
                .onEnded{v in defer{drag=.zero};if case .second(true,let d?)=v{onMove(d.translation)}}
        )
    }
}

'''
s=s.replace(card_anchor,new_cards+card_anchor,1)

# Fix a Color equality expression that SwiftUI Color cannot compare. Use opacity
# directly and let neutral tracks simply inherit their subtle color.
s=s.replace('.background(color.opacity(color==Color.primary.opacity(0.10) ? 0.55:0.88),in:RoundedRectangle(cornerRadius:6))','.background(color.opacity(0.88),in:RoundedRectangle(cornerRadius:6))')

p.write_text(s)
print('Applied VeloCut v0.6.1 completely fresh editor UI')
