from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

s = s.replace(
    '@State private var expandedLanes:Set<Int>=[]',
    '@State private var expandedLanes:Set<Int>=[]\n    @State private var timelineMagnificationBase:Double?\n    @State private var showFullscreenPreview=false\n    @State private var laneHeights:[Int:CGFloat]=[0:46,1:46,2:46]'
)

s = s.replace(
    '.sheet(isPresented:$model.isFileImporting)',
    '.fullScreenCover(isPresented:$showFullscreenPreview){FullscreenPreviewV4(player:model.player,onClose:{showFullscreenPreview=false})}\n        .sheet(isPresented:$model.isFileImporting)',
    1
)

preview_pattern = re.compile(r'^\s*private var preview:some View.*$', re.M)
preview_replacement = r'''    private var preview:some View {
        GeometryReader { g in
            ZStack {
                RoundedRectangle(cornerRadius:22).fill(.black)
                if !model.clips.isEmpty {
                    PlayerView(player:model.player).clipShape(RoundedRectangle(cornerRadius:22))
                    if !model.overlayText.isEmpty {
                        Text(model.overlayText)
                            .font(.system(size:model.overlayTextSize,weight:.bold))
                            .foregroundStyle(.white)
                            .shadow(radius:4)
                            .position(x:g.size.width/2,y:g.size.height*model.overlayTextY)
                    }
                    VStack {
                        HStack {
                            Spacer()
                            Button { showFullscreenPreview = true } label: {
                                Image(systemName:"arrow.up.left.and.arrow.down.right")
                                    .font(.system(size:13,weight:.bold))
                                    .foregroundStyle(.white)
                                    .frame(width:36,height:36)
                                    .background(.ultraThinMaterial,in:Circle())
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                    }
                    .padding(10)
                } else {
                    VStack(spacing:14) {
                        Image(systemName:"film.stack").font(.system(size:42)).foregroundStyle(.white)
                        Text("Добавить видео").foregroundStyle(.white)
                        PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos) {
                            Label("Из Фото",systemImage:"photo")
                                .padding(.horizontal,16)
                                .frame(height:38)
                                .background(.white,in:Capsule())
                                .foregroundStyle(.black)
                        }
                    }
                }
                if model.isPreviewCaching {
                    VStack {
                        HStack { ProgressView().controlSize(.mini); Text("Кеш превью") }
                            .font(.caption2)
                            .padding(7)
                            .background(.ultraThinMaterial,in:Capsule())
                        Spacer()
                    }
                    .padding(10)
                }
            }
        }
        .padding(.horizontal,10)
        .padding(.top,8)
    }'''
s, count = preview_pattern.subn(preview_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Preview block was not found')

s = s.replace(
    'Button{model.timelineZoom=max(.55,model.timelineZoom-.2)}label:{Image(systemName:"minus.magnifyingglass")};Button{model.timelineZoom=min(3.2,model.timelineZoom+.2)}label:{Image(systemName:"plus.magnifyingglass")}',
    'Button{model.timelineZoom=max(0.35,model.timelineZoom-0.2)}label:{Image(systemName:"minus.magnifyingglass")};Button{model.timelineZoom=min(8.0,model.timelineZoom+0.2)}label:{Image(systemName:"plus.magnifyingglass")}'
)

s = s.replace(
    'GeometryReader{geo in timelineCanvas(geo)}.frame(minHeight:230)',
    'ScrollView(.vertical,showsIndicators:false){GeometryReader{geo in timelineCanvas(geo)}.frame(height:timelineRequiredHeight)}.frame(minHeight:230,maxHeight:360)'
)

s = s.replace(
    'let pps=34.0*model.timelineZoom, center=geo.size.width/2, rulerH=22.0, fxH=42.0, videoH=46.0, curveH=34.0\n        let laneTop:(Int)->CGFloat={lane in var y=rulerH+fxH;for l in 0..<lane{y += videoH + (expandedLanes.contains(l) ? curveH:0)};return y}',
    'let pps=34.0*model.timelineZoom, center=geo.size.width/2, rulerH=22.0, fxH=42.0, curveH=56.0\n        let laneHeight:(Int)->CGFloat={laneHeights[$0] ?? 46}\n        let laneTop:(Int)->CGFloat={lane in var y=rulerH+fxH;for l in 0..<lane{y += laneHeight(l) + (expandedLanes.contains(l) ? curveH:0)};return y}'
)

fx_pattern = re.compile(r'^\s*ForEach\(model\.speedFX\)\{fx in .*$', re.M)
fx_replacement = '''            ForEach(model.speedFX){fx in
                let w=max(48,fx.duration*pps),x=center+(fx.start-model.projectTime)*pps+w/2
                SpeedFXBlock(
                    fx:fx,
                    width:w,
                    onOpen:{curveTarget = .global(fx.id)},
                    onMove:{model.moveSpeedFX(fx.id,delta:Double($0.width)/pps)},
                    onDuplicate:{model.duplicateSpeedFX(fx.id)},
                    onAtPlayhead:{model.duplicateSpeedFX(fx.id,atPlayhead:true)},
                    onRepeat:{model.repeatSpeedFX(fx.id,count:4)},
                    onDelete:{model.deleteSpeedFX(fx.id)}
                )
                .position(x:x,y:rulerH+fxH/2)

                SpeedFXEdgeHandleV4(
                    leading:true,
                    start:fx.start,
                    duration:fx.duration,
                    pps:pps,
                    onBegin:{model.beginInteractiveEdit()},
                    onChange:{newStart,newDuration in model.setSpeedFXStartInteractive(fx.id,start:newStart,duration:newDuration)}
                )
                .position(x:x-w/2+5,y:rulerH+fxH/2)

                SpeedFXEdgeHandleV4(
                    leading:false,
                    start:fx.start,
                    duration:fx.duration,
                    pps:pps,
                    onBegin:{model.beginInteractiveEdit()},
                    onChange:{_,newDuration in model.setSpeedFXDurationInteractive(fx.id,newDuration)}
                )
                .position(x:x+w/2-5,y:rulerH+fxH/2)
            }'''
s, count = fx_pattern.subn(fx_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Speed FX timeline block was not found')

lane_pattern = re.compile(r'^\s*ForEach\(0<\.\.<3,id:\\\.self\)\{lane in .*$', re.M)
lane_replacement = '''            ForEach(0..<3,id:\\.self){lane in
                let top=laneTop(lane),h=laneHeight(lane)
                RoundedRectangle(cornerRadius:8)
                    .fill(Color.secondary.opacity(0.06))
                    .frame(height:max(35,h-3))
                    .offset(y:top)

                Button {
                    if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}
                } label: {
                    HStack(spacing:3){
                        Text("V\\(lane+1)")
                        Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down")
                    }
                    .font(.system(size:9,weight:.bold))
                    .padding(4)
                    .background(.thinMaterial,in:Capsule())
                }
                .buttonStyle(.plain)
                .position(x:24,y:top+12)

                LaneHeightHandleV4(height:h){laneHeights[lane]=$0}
                    .position(x:geo.size.width-22,y:top+h-7)

                if expandedLanes.contains(lane){
                    RoundedRectangle(cornerRadius:7)
                        .fill(Color.accentColor.opacity(0.035))
                        .frame(height:curveH-2)
                        .offset(y:top+h)
                    Text("Speed")
                        .font(.system(size:8,weight:.semibold))
                        .foregroundStyle(.secondary)
                        .position(x:22,y:top+h+10)
                }
            }'''
s, count = lane_pattern.subn(lane_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Lane block was not found')

clip_pattern = re.compile(r'^\s*ForEach\(Array\(model\.layouts\.enumerated\(\)\),id:\\\.element\.id\)\{index,l in .*$', re.M)
clip_replacement = '''            ForEach(Array(model.layouts.enumerated()),id:\\.element.id){index,l in
                let w=max(52,l.duration*pps),x=center+(l.start-model.projectTime)*pps+w/2,top=laneTop(l.clip.track),h=laneHeight(l.clip.track)
                ResizableTimelineClipCardV4(
                    clip:l.clip,
                    index:index,
                    width:w,
                    height:max(40,h-6),
                    selected:l.id==model.selectedClipID,
                    onTap:{model.selectClip(l.id)},
                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{model.moveClip(l.id,translation:$0,pps:pps)}
                )
                .position(x:x,y:top+h/2)

                if l.id == model.selectedClipID {
                    let sourcePerOutput = l.clip.sourceDuration / max(l.duration,0.01)
                    TimelineTrimHandleV4(
                        leading:true,
                        currentValue:l.clip.trimStart,
                        pps:pps,
                        sourcePerOutput:sourcePerOutput,
                        height:max(28,h-10),
                        onBegin:{model.beginInteractiveEdit()},
                        onChange:{model.setTrimStartInteractive(l.id,$0)}
                    )
                    .position(x:x-w/2+6,y:top+h/2)

                    TimelineTrimHandleV4(
                        leading:false,
                        currentValue:l.clip.trimEnd,
                        pps:pps,
                        sourcePerOutput:sourcePerOutput,
                        height:max(28,h-10),
                        onBegin:{model.beginInteractiveEdit()},
                        onChange:{model.setTrimEndInteractive(l.id,$0)}
                    )
                    .position(x:x+w/2-6,y:top+h/2)
                }

                if expandedLanes.contains(l.clip.track) {
                    InlineCurveEditorV4(
                        model:model,
                        target:.clip(l.id),
                        onOpen:{model.selectedClipID=l.id;curveTarget = .clip(l.id)}
                    )
                    .frame(width:w,height:curveH-5)
                    .position(x:x,y:top+h+curveH/2)
                }
            }'''
s, count = clip_pattern.subn(clip_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Clip timeline block was not found')

gesture_pattern = re.compile(r'^\s*\}\.clipped\(\)\.contentShape\(Rectangle\(\)\)\.gesture\(DragGesture\(minimumDistance:12\).*$', re.M)
gesture_replacement = '''        }
        .clipped()
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance:2)
                .onChanged{v in
                    if timelineDragStart==nil { timelineDragStart=model.projectTime;model.beginScrub() }
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)
                }
                .onEnded{_ in timelineDragStart=nil;model.endScrub()}
        )
        .simultaneousGesture(
            MagnificationGesture()
                .onChanged{value in
                    if timelineMagnificationBase==nil { timelineMagnificationBase=model.timelineZoom }
                    model.timelineZoom=min(8.0,max(0.35,(timelineMagnificationBase ?? model.timelineZoom)*Double(value)))
                }
                .onEnded{_ in timelineMagnificationBase=nil}
        )'''
s, count = gesture_pattern.subn(gesture_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Timeline gesture block was not found')

s = s.replace(
    '    private var bottomBar:some View{',
    '''    private var timelineRequiredHeight:CGFloat {
        let base:CGFloat = 22 + 42 + 12
        let video = (0..<3).reduce(CGFloat.zero) { $0 + (laneHeights[$1] ?? 46) }
        let curves = CGFloat(expandedLanes.count) * 56
        return max(230,base+video+curves)
    }

    private var bottomBar:some View{''',
    1
)

curve_pattern = re.compile(r'^struct CurveEditorPanel:View.*$', re.M)
curve_replacement = r'''struct CurveEditorPanel:View {
    @ObservedObject var model:EditorViewModel
    let target:CurveTarget
    let onClose:()->Void
    @State private var selectedPoint:UUID?

    var body:some View {
        VStack(spacing:10) {
            HStack {
                Button(action:onClose) { Image(systemName:"chevron.down.circle.fill").font(.title2) }
                VStack(alignment:.leading) {
                    Text(title).font(.headline)
                    Text("Перетаскивайте точки • двойной тап добавляет точку").font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    ForEach(SpeedCurvePreset.all) { p in Button(p.name) { model.applyPreset(p,to:target) } }
                } label: {
                    Label("Шаблон",systemImage:"sparkles").font(.caption)
                }
            }
            .padding(.horizontal,14)

            ScrollView(.horizontal,showsIndicators:false) {
                HStack(spacing:8) {
                    ForEach(SpeedCurvePreset.all) { p in
                        Button { model.applyPreset(p,to:target) } label: {
                            VStack(spacing:3) {
                                CurveThumbnail(curve:p.curve,lineWidth:1.5).frame(width:74,height:28)
                                Text(p.name).font(.system(size:8))
                            }
                            .padding(6)
                            .background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal,12)
            }

            VStack(spacing:4) {
                Slider(
                    value:Binding(
                        get:{model.normalizedPlayhead(for:target)},
                        set:{model.seekCurveTarget(target,normalized:$0)}
                    ),
                    in:0...1
                )
                HStack {
                    Text(timeText(0))
                    Spacer()
                    Text(timeText(model.normalizedPlayhead(for:target))).fontWeight(.semibold)
                    Spacer()
                    Text(timeText(1))
                }
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal,14)

            CurveEditorGraphV4(model:model,target:target,selectedPointID:$selectedPoint)
                .frame(minHeight:180)
                .padding(.horizontal,12)

            HStack {
                Button { model.addCurvePoint(target,t:model.normalizedPlayhead(for:target)) } label: { Label("Точка",systemImage:"plus.circle") }
                Button { model.mirrorCurve(target) } label: { Label("Mirror",systemImage:"arrow.left.and.right") }
                if let id=selectedPoint {
                    Button(role:.destructive) { model.deleteCurvePoint(target,pointID:id);selectedPoint=nil } label: { Image(systemName:"trash") }
                }
                Spacer()
                Picker("",selection:Binding(get:{model.curve(for:target).interpolation},set:{model.setCurveInterpolation(target,$0)})) {
                    ForEach(CurveInterpolation.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.menu)
            }
            .font(.caption)
            .padding(.horizontal,14)

            if case .global(let id)=target,let fx=model.speedFX.first(where:{$0.id==id}) {
                VStack(spacing:8) {
                    HStack {
                        Text("Strength")
                        Slider(value:Binding(get:{fx.strength},set:{model.setSpeedFXStrength(id,$0)}),in:0...2)
                        Text("\(fx.strength,specifier:"%.1f")×").monospacedDigit()
                    }
                    HStack {
                        Text("Длина")
                        Slider(value:Binding(get:{fx.duration},set:{model.setSpeedFXDuration(id,$0)}),in:0.15...4)
                        Text("\(fx.duration,specifier:"%.2f")с").monospacedDigit()
                    }
                    HStack {
                        Picker("Режим",selection:Binding(get:{fx.mode},set:{model.setSpeedFXMode(id,$0)})) {
                            ForEach(SpeedFXMode.allCases) { Text($0.rawValue).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        Button { model.duplicateSpeedFX(id) } label: { Image(systemName:"plus.square.on.square") }
                        Button { model.repeatSpeedFX(id,count:4) } label: { Text("×4") }
                    }
                }
                .font(.caption)
                .padding(.horizontal,14)
            }
            Spacer(minLength:4)
        }
        .padding(.vertical,8)
        .background(.regularMaterial)
    }

    private var title:String {
        switch target {
        case .clip:return "Speed Curve клипа"
        case .global:return "Global Speed FX"
        }
    }

    private func timeText(_ normalized:Double)->String {
        String(format:"%.2fс",model.curveProjectTime(target,normalized:normalized))
    }
}'''
s, count = curve_pattern.subn(curve_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Curve editor block was not found')

s = s.replace('min(max(value, 0, ), 2)', 'min(max(value, 0), 2)')
s = re.sub(r'(?<![A-Za-z0-9_.])\.(\d+)', r'0.\1', s)
s = re.sub(r'(?<![<>=!+\-*/%&|^])\s*=\s*(?!=)', ' = ', s)
s = re.sub(r'(?<=[A-Za-z0-9_)])([+-])(?=0\.\d)', r' \1 ', s)
s = s.replace('drag=.zero', 'drag = .zero')
s = s.replace('c.videoGravity=.resizeAspect', 'c.videoGravity = .resizeAspect')
s = s.replace('session.outputFileType=.mp4', 'session.outputFileType = .mp4')

p.write_text(s)
print('Patched original v0.4 editor with v0.4.2 interactions')