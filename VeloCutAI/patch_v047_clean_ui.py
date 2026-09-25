from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# Project loop state shown in the compact preview controls.
s = s.replace(
    '@Published var speedProcessingMode: SpeedProcessingMode = .fast\n    @Published var isMerging = false',
    '@Published var speedProcessingMode: SpeedProcessingMode = .fast\n    @Published var isMerging = false\n    @Published var projectLoopEnabled = false',
    1
)

# Loop the complete project when the preview Loop button is enabled.
old_boundary = 'if projectTime >= projectDuration - 0.02 { player.pause(); isPlaying = false; if returnPlayheadAfterStop { seekProject(to: playbackStart, exact: true) } }'
new_boundary = 'if projectTime >= projectDuration - 0.02 { if projectLoopEnabled { seekProject(to:0,exact:true); player.play(); isPlaying=true } else { player.pause(); isPlaying=false; if returnPlayheadAfterStop { seekProject(to:playbackStart,exact:true) } } }'
if old_boundary not in s:
    raise RuntimeError('project playback boundary not found')
s = s.replace(old_boundary, new_boundary, 1)

# Remove the top bar and separate playback row. Preview becomes the complete top area.
old_stack = 'ZStack{Color(uiColor:.systemGroupedBackground).ignoresSafeArea();VStack(spacing:0){topBar;preview.frame(height:min(335,max(215,root.size.height*0.34)));playback;if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{timeline.frame(maxHeight:.infinity)};bottomBar}.frame(width:root.size.width,height:root.size.height,alignment:.top)}'
new_stack = 'ZStack{Color(uiColor:.systemGroupedBackground).ignoresSafeArea();VStack(spacing:0){preview.frame(height:min(390,max(255,root.size.height*0.42))).ignoresSafeArea(edges:.top);if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{timeline.frame(maxHeight:.infinity)};bottomBar}.frame(width:root.size.width,height:root.size.height,alignment:.top)}'
if old_stack not in s:
    raise RuntimeError('v0.4.6 editor stack not found')
s = s.replace(old_stack, new_stack, 1)

# Replace Preview with a clean edge-to-edge preview. One menu button at the top-right;
# one playback strip at the lower-right: Loop, Play/Pause, Undo, Redo.
preview_pattern = re.compile(r'    private var preview:some View\{.*?\n\n    private var playback:', re.S)
preview_replacement = r'''    private var preview:some View{
        GeometryReader{g in
            ZStack{
                Rectangle().fill(.black)
                if !model.clips.isEmpty {
                    PlayerView(player:model.player)
                    if !model.overlayText.isEmpty {
                        Text(model.overlayText)
                            .font(.system(size:model.overlayTextSize,weight:.bold))
                            .foregroundStyle(.white)
                            .shadow(radius:4)
                            .position(x:g.size.width/2,y:g.size.height*model.overlayTextY)
                    }
                } else {
                    VStack(spacing:14){
                        Image(systemName:"film.stack").font(.system(size:42)).foregroundStyle(.white)
                        Text("Добавить видео").foregroundStyle(.white)
                        PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos){
                            Label("Из Фото",systemImage:"photo")
                                .padding(.horizontal,16)
                                .frame(height:38)
                                .background(.white,in:Capsule())
                                .foregroundStyle(.black)
                        }
                    }
                }

                VStack(spacing:0){
                    HStack{
                        Spacer()
                        Menu{
                            Button{inspector = .export}label:{Label("Экспорт",systemImage:"square.and.arrow.up")}.disabled(model.clips.isEmpty)
                            PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos){Label("Импорт из Фото",systemImage:"photo.on.rectangle")}
                            Button{model.isFileImporting=true}label:{Label("Импорт из Файлов",systemImage:"folder")}
                        }label:{
                            Image(systemName:"ellipsis.circle.fill")
                                .font(.system(size:25,weight:.semibold))
                                .foregroundStyle(.white)
                                .shadow(radius:3)
                                .frame(width:44,height:44)
                        }
                    }
                    .padding(.top,4)
                    .padding(.trailing,8)

                    Spacer()

                    HStack{
                        Spacer()
                        HStack(spacing:6){
                            Button{
                                model.projectLoopEnabled.toggle()
                                model.playbackMode = .project
                                model.haptic(.selection)
                            }label:{
                                Image(systemName:model.projectLoopEnabled ? "repeat.circle.fill":"repeat")
                                    .frame(width:30,height:30)
                            }
                            Button{model.playPause()}label:{
                                Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                                    .frame(width:30,height:30)
                            }
                            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:30,height:30)}.disabled(!model.canUndo)
                            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:30,height:30)}.disabled(!model.canRedo)
                        }
                        .font(.system(size:14,weight:.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal,7)
                        .padding(.vertical,4)
                        .background(.ultraThinMaterial,in:Capsule())
                    }
                    .padding(.trailing,10)
                    .padding(.bottom,8)
                }

                if model.isPreviewCaching {
                    VStack{
                        HStack{
                            ProgressView().controlSize(.mini)
                            Text("Кеш превью")
                        }
                        .font(.caption2)
                        .padding(7)
                        .background(.ultraThinMaterial,in:Capsule())
                        Spacer()
                    }
                    .padding(.top,10)
                    .padding(.leading,10)
                    .frame(maxWidth:.infinity,alignment:.leading)
                }
            }
        }
    }

    private var playback:'''
s, count = preview_pattern.subn(preview_replacement, s, count=1)
if count != 1:
    raise RuntimeError('preview block not found')

# Speed FX is no longer a built-in preset menu. It creates a neutral 1x curve.
s, count = re.subn(
    r'Menu\{ForEach\(SpeedCurvePreset\.all\.prefix\(12\)\)\{preset in Button\(preset\.name\)\{model\.addSpeedFX\(preset:preset\)\}\}\}label:\{Label\("Speed FX",systemImage:"waveform\.path\.ecg\.rectangle"\)\.font\(\.caption\)\}',
    'Button{model.addFlatSpeedFX()}label:{Label("Speed FX",systemImage:"waveform.path.ecg.rectangle").font(.caption)}',
    s,
    count=1
)
if count != 1:
    raise RuntimeError('Speed FX preset menu not found')

# Replace the complete curve editor: no built-in templates; saved user curves only;
# playback controls are on the right; vertical scrolling + bottom safe-area padding.
curve_pattern = re.compile(r'struct CurveEditorPanel:View \{.*?\n\}\n\nstruct InspectorSheet:View', re.S)
curve_replacement = r'''struct CurveEditorPanel:View {
    @ObservedObject var model:EditorViewModel
    let target:CurveTarget
    let onClose:()->Void
    @State private var selectedPoint:UUID?
    @State private var showSaveCurve=false
    @State private var curveName=""

    var body:some View {
        ScrollView(.vertical,showsIndicators:true) {
            VStack(spacing:10) {
                HStack(spacing:8) {
                    Button(action:onClose) { Image(systemName:"chevron.down.circle.fill").font(.title2) }
                    VStack(alignment:.leading,spacing:2) {
                        Text(title).font(.headline)
                        Text("Точки и направляющие редактируются пальцем")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength:8)
                    Button { model.playCurveFromStart(target) } label: {
                        Image(systemName:"backward.end.fill").frame(width:26,height:22)
                    }
                    .buttonStyle(.bordered)
                    Button { model.toggleCurvePlayback() } label: {
                        Image(systemName:model.isPlaying ? "pause.fill":"play.fill").frame(width:26,height:22)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(.horizontal,14)

                if !model.savedCurves.isEmpty {
                    VStack(alignment:.leading,spacing:5) {
                        Text("Мои кривые").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ScrollView(.horizontal,showsIndicators:false) {
                            HStack(spacing:8) {
                                ForEach(model.savedCurves) { saved in
                                    Menu {
                                        Button("Применить") { model.applySavedCurve(saved,to:target) }
                                        Button("Удалить",role:.destructive) { model.deleteSavedCurve(saved) }
                                    } label: {
                                        VStack(spacing:3) {
                                            CurveThumbnail(curve:saved.curve,lineWidth:1.5).frame(width:74,height:28)
                                            Text(saved.name).font(.system(size:8)).lineLimit(1)
                                        }
                                        .frame(width:82)
                                        .padding(6)
                                        .background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal,14)
                }

                HStack(spacing:8) {
                    Text("Кадры").font(.caption2).foregroundStyle(.secondary)
                    Picker("Кадры",selection:$model.speedProcessingMode) {
                        ForEach(SpeedProcessingMode.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .frame(width:150)
                    Spacer()
                    Text(model.speedProcessingMode == .smooth ? "Smooth remap" : "Fast preview")
                        .font(.system(size:8))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal,14)

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
                        Text(String(format:"%.2fс",model.curveProjectTime(target,normalized:model.normalizedPlayhead(for:target))))
                            .font(.caption2.weight(.semibold))
                        Spacer()
                        Text(timeText(1))
                    }
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                }
                .padding(.horizontal,14)

                CurveEditorGraphV4(model:model,target:target,selectedPointID:$selectedPoint)
                    .frame(height:210)
                    .padding(.horizontal,12)

                if let pointID=selectedPoint, let point=model.curve(for:target).points.first(where:{$0.id==pointID}) {
                    HStack(spacing:10) {
                        Text(String(format:"%.2f×",point.speed))
                            .font(.caption.monospacedDigit().weight(.semibold))
                        CurveModeTabsV45(mode:point.mode) { newMode in
                            model.setCurvePointMode(target,pointID:pointID,mode:newMode,resetHandles:newMode == .smooth)
                        }
                        if point.mode != .linear {
                            Button { model.resetCurvePointHandles(target,pointID:pointID) } label: {
                                Image(systemName:"arrow.counterclockwise")
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .padding(.horizontal,14)
                }

                HStack(spacing:8) {
                    Button { model.addCurvePoint(target,t:model.normalizedPlayhead(for:target)) } label: {
                        Label("Точка",systemImage:"plus.circle")
                    }
                    Button { model.mirrorCurve(target) } label: {
                        Label("Mirror",systemImage:"arrow.left.and.right")
                    }
                    Button { showSaveCurve=true } label: {
                        Label("Сохранить",systemImage:"square.and.arrow.down")
                    }
                    if let id=selectedPoint {
                        Button(role:.destructive) { model.deleteCurvePoint(target,pointID:id);selectedPoint=nil } label: {
                            Image(systemName:"trash")
                        }
                    }
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
            }
            .padding(.top,8)
            .padding(.bottom,24)
        }
        .safeAreaPadding(.bottom,10)
        .background(.regularMaterial)
        .alert("Сохранить кривую",isPresented:$showSaveCurve) {
            TextField("Название",text:$curveName)
            Button("Сохранить") {
                model.saveCurve(target,name:curveName)
                curveName=""
            }
            Button("Отмена",role:.cancel) { curveName="" }
        } message: {
            Text("Кривая сохранится в разделе «Мои кривые».")
        }
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
}

struct InspectorSheet:View'''
s, count = curve_pattern.subn(curve_replacement, s, count=1)
if count != 1:
    raise RuntimeError('CurveEditorPanel block not found')

# Speed inspector has no built-in preset carousel. It shows only the flat curve,
# saved user curves, the editor button, and neutral Global Speed FX creation.
speed_pattern = re.compile(r'    private var speed:some View\{.*?\n    private var audio:', re.S)
speed_replacement = r'''    private var speed:some View{
        VStack(spacing:14){
            Picker("",selection:$speedTab){Text("Обычная").tag(0);Text("Кривые").tag(1)}.pickerStyle(.segmented)
            if speedTab==0 {
                Text("\(model.selectedClip?.baseSpeed ?? 1,specifier:"%.2f")×")
                    .font(.system(size:36,weight:.semibold,design:.rounded))
                Slider(value:Binding(get:{model.selectedClip?.baseSpeed ?? 1},set:{model.setBaseSpeed($0)}),in:.05...20)
                HStack{ForEach([0.25,0.5,1,2,5,10,20],id:\.self){v in Button("\(v,specifier:"%g")×"){model.setBaseSpeed(v)}.font(.caption).buttonStyle(.bordered)}}
            } else if let id=model.selectedClipID {
                Toggle("Кривая скорости",isOn:Binding(get:{model.selectedClip?.curveEnabled ?? false},set:{model.setCurveEnabled(id,$0)}))
                HStack {
                    CurveThumbnail(curve:model.selectedClip?.speedCurve ?? .flat,lineWidth:1.8)
                        .frame(height:46)
                    VStack(alignment:.leading,spacing:2){
                        Text("Начальная кривая 1×").font(.caption.weight(.semibold))
                        Text("Добавляйте и перемещайте точки вручную").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .padding(8)
                .background(.thinMaterial,in:RoundedRectangle(cornerRadius:12))

                if !model.savedCurves.isEmpty {
                    VStack(alignment:.leading,spacing:5) {
                        Text("Мои кривые").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ScrollView(.horizontal,showsIndicators:false) {
                            HStack(spacing:8) {
                                ForEach(model.savedCurves) { saved in
                                    Menu {
                                        Button("Применить") { model.applySavedCurve(saved,to:.clip(id)) }
                                        Button("Удалить",role:.destructive) { model.deleteSavedCurve(saved) }
                                    } label: {
                                        VStack(spacing:3){
                                            CurveThumbnail(curve:saved.curve,lineWidth:1.5).frame(width:76,height:30)
                                            Text(saved.name).font(.system(size:8)).lineLimit(1)
                                        }
                                        .padding(6)
                                        .background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))
                                    }
                                }
                            }
                        }
                    }
                }

                Button{curveTarget = .clip(id);dismiss()}label:{
                    Label("Открыть редактор кривой",systemImage:"arrow.up.left.and.arrow.down.right").frame(maxWidth:.infinity)
                }
                .buttonStyle(.borderedProminent)

                Button{model.addFlatSpeedFX()}label:{
                    Label("Добавить Global Speed FX",systemImage:"waveform.path.ecg.rectangle")
                }
            }
            Spacer()
        }
        .padding(.top,8)
    }
    private var audio:'''
s, count = speed_pattern.subn(speed_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Inspector speed block not found')

p.write_text(s)
print('Applied VeloCut v0.4.7 clean preview, neutral Speed FX, saved curves and safe curve editor')
