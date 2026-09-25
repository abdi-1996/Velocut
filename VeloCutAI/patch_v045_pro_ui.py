from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# View model state for merge and speed processing quality.
s = s.replace(
    '@Published var exportQuality: ExportQuality = .fullHD',
    '@Published var exportQuality: ExportQuality = .fullHD\n    @Published var speedProcessingMode: SpeedProcessingMode = .fast\n    @Published var isMerging = false',
    1
)

# Smooth mode uses a denser time-remap. This improves ramp smoothness while
# keeping Fast lighter for preview. It is not optical-flow synthesis.
s = s.replace(
    'let segments = (clip.curveEnabled || !speedFX.isEmpty) ? 48 : 1',
    'let segments = (clip.curveEnabled || !speedFX.isEmpty) ? (speedProcessingMode == .smooth ? 120 : 48) : 1',
    1
)

merge_method = r'''
    func mergeClips(_ ids: [UUID]) {
        let chosen = clips.enumerated().filter { ids.contains($0.element.id) }.sorted { $0.offset < $1.offset }
        guard chosen.count == 2 else { errorMessage = "Выберите два клипа для Merge"; return }
        player.pause(); isPlaying = false; isMerging = true

        Task {
            do {
                let composition = AVMutableComposition()
                guard let video = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
                    throw NSError(domain: "VeloCut", code: 41, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать Merge видеодорожку"])
                }
                let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
                var cursor = CMTime.zero
                var firstTransform: CGAffineTransform?

                for (_, clip) in chosen {
                    let source = asset(for: clip.url)
                    guard let sourceVideo = try await source.loadTracks(withMediaType: .video).first else { continue }
                    if firstTransform == nil { firstTransform = try await sourceVideo.load(.preferredTransform) }
                    let sourceAudio = try await source.loadTracks(withMediaType: .audio).first
                    let segments = clip.curveEnabled ? (speedProcessingMode == .smooth ? 120 : 48) : 1
                    let sourceStep = clip.sourceDuration / Double(segments)

                    for index in 0..<segments {
                        let normalized = (Double(index) + 0.5) / Double(segments)
                        let speed = clampSpeed(clip.baseSpeed * (clip.curveEnabled ? clip.speedCurve.value(at: normalized) : 1))
                        let sourceRange = CMTimeRange(
                            start: CMTime(seconds: clip.trimStart + Double(index) * sourceStep, preferredTimescale: 6000),
                            duration: CMTime(seconds: sourceStep, preferredTimescale: 6000)
                        )
                        try video.insertTimeRange(sourceRange, of: sourceVideo, at: cursor)
                        if let sourceAudio, let audio { try? audio.insertTimeRange(sourceRange, of: sourceAudio, at: cursor) }
                        let inserted = CMTimeRange(start: cursor, duration: CMTime(seconds: sourceStep, preferredTimescale: 6000))
                        let outputDuration = CMTime(seconds: sourceStep / speed, preferredTimescale: 6000)
                        video.scaleTimeRange(inserted, toDuration: outputDuration)
                        if let audio { audio.scaleTimeRange(inserted, toDuration: outputDuration) }
                        cursor = cursor + outputDuration
                    }
                }

                if let firstTransform { video.preferredTransform = firstTransform }
                let output = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-Merge-\(UUID().uuidString).mp4")
                guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
                    throw NSError(domain: "VeloCut", code: 42, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать Merge export"])
                }
                session.outputURL = output
                session.outputFileType = .mp4
                session.shouldOptimizeForNetworkUse = true
                await withCheckedContinuation { continuation in
                    session.exportAsynchronously { continuation.resume() }
                }
                guard session.status == .completed else {
                    throw session.error ?? NSError(domain: "VeloCut", code: 43, userInfo: [NSLocalizedDescriptionKey: "Merge не завершён"])
                }

                let duration = max(0.05, CMTimeGetSeconds(try await asset(for: output).load(.duration)))
                registerUndo()
                let insertionIndex = chosen.first?.offset ?? 0
                let lane = chosen.first?.element.track ?? 0
                clips.removeAll { ids.contains($0.id) }
                let merged = EditorClip(
                    url: output,
                    name: "Merged Clip",
                    duration: duration,
                    trimStart: 0,
                    trimEnd: duration,
                    baseSpeed: 1,
                    volume: 1,
                    track: lane,
                    curveEnabled: false,
                    speedCurve: .flat
                )
                clips.insert(merged, at: min(insertionIndex, clips.count))
                selectedClipID = merged.id
                projectTime = projectStart(of: merged.id)
                schedulePreview(immediate: true)
                haptic(.medium)
            } catch {
                errorMessage = "Merge: \(error.localizedDescription)"
            }
            isMerging = false
        }
    }

'''
if '// MARK: Curves' not in s:
    raise RuntimeError('Curve marker not found for merge insertion')
s = s.replace('    // MARK: Curves\n', merge_method + '    // MARK: Curves\n', 1)

# Extra UI state.
s = s.replace(
    '@State private var laneHeights:[Int:CGFloat]=[0:46,1:46,2:46]',
    '@State private var laneHeights:[Int:CGFloat]=[0:46,1:46,2:46]\n    @State private var multiSelectMode=false\n    @State private var multiSelectedClips:Set<UUID>=[]',
    1
)

# Preview sits directly beneath the compact top bar.
s = s.replace(
    'preview.frame(height:min(350,max(220,root.size.height*0.37)))',
    'preview.frame(height:min(335,max(215,root.size.height*0.34)))',
    1
)
s = s.replace('.padding(.horizontal,10).padding(.top,8)', '.padding(.horizontal,6).padding(.top,0)', 1)

# Compact top controls.
top_pattern = re.compile(r'    private var topBar:some View\{.*?\n\n    private var preview:', re.S)
top_replacement = r'''    private var topBar:some View{
        HStack(spacing:6){
            VStack(alignment:.leading,spacing:0){
                Text("VeloCut").font(.system(size:17,weight:.bold))
                Text("\(model.clips.count) клип. • \(format(model.projectDuration))").font(.system(size:9)).foregroundStyle(.secondary)
            }
            Spacer(minLength:4)
            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:26,height:26)}.disabled(!model.canUndo)
            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:26,height:26)}.disabled(!model.canRedo)
            PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos){Image(systemName:"photo.on.rectangle").frame(width:27,height:27)}
            Button{model.isFileImporting=true}label:{Image(systemName:"folder").frame(width:27,height:27)}
            Button{inspector = .export}label:{Image(systemName:"square.and.arrow.up").font(.system(size:13,weight:.bold)).frame(width:30,height:30).background(Color.accentColor,in:Circle()).foregroundStyle(.white)}.disabled(model.clips.isEmpty)
        }
        .padding(.horizontal,10)
        .padding(.vertical,4)
        .background(.ultraThinMaterial)
    }

    private var preview:'''
s, count = top_pattern.subn(top_replacement, s, count=1)
if count != 1:
    raise RuntimeError('topBar block not found')

# Slim playback controls: remove duplicated +/-10 controls and keep essentials.
play_pattern = re.compile(r'    private var playback:some View\{.*?\n\n    private var timeline:', re.S)
play_replacement = r'''    private var playback:some View{
        HStack(spacing:9){
            Button{model.seekProject(to:0,exact:true)}label:{Image(systemName:"backward.end.fill").frame(width:28,height:28)}
            Button{model.playPause()}label:{Image(systemName:model.isPlaying ? "pause.fill":"play.fill").font(.system(size:16,weight:.bold)).frame(width:40,height:30).background(.thinMaterial,in:Capsule())}
            Menu{Picker("Режим",selection:$model.playbackMode){ForEach(PlaybackMode.allCases){Label($0.rawValue,systemImage:$0.icon).tag($0)}};Toggle("Вернуть playhead",isOn:$model.returnPlayheadAfterStop)}label:{Image(systemName:model.playbackMode.icon).frame(width:28,height:28).background(.thinMaterial,in:Circle())}
            Spacer()
            Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))").font(.system(size:10,design:.monospaced)).foregroundStyle(.secondary)
        }
        .padding(.horizontal,12)
        .padding(.vertical,5)
        .disabled(model.clips.isEmpty)
    }

    private var timeline:'''
s, count = play_pattern.subn(play_replacement, s, count=1)
if count != 1:
    raise RuntimeError('playback block not found')

# Multi-select / Merge controls in timeline header.
header_pattern = re.compile(r'HStack\{Label\("Таймлайн",systemImage:"timeline\.selection"\).*?\}\.padding\(\.horizontal,14\)\.foregroundStyle\(\.secondary\)', re.S)
header_replacement = r'''HStack(spacing:8){
            Label("Таймлайн",systemImage:"timeline.selection").font(.caption.weight(.semibold))
            Button{
                multiSelectMode.toggle()
                if !multiSelectMode { multiSelectedClips.removeAll() }
            }label:{Label(multiSelectMode ? "\(multiSelectedClips.count)/2":"Выбор",systemImage:multiSelectMode ? "checkmark.circle":"checkmark.circle.badge.questionmark").font(.caption)}
            if multiSelectMode && multiSelectedClips.count == 2 {
                Button{
                    model.mergeClips(Array(multiSelectedClips))
                    multiSelectedClips.removeAll();multiSelectMode=false
                }label:{Label("Merge",systemImage:"rectangle.2.swap").font(.caption.weight(.semibold))}
                .disabled(model.isMerging)
            }
            Spacer()
            Menu{ForEach(SpeedCurvePreset.all.prefix(12)){preset in Button(preset.name){model.addSpeedFX(preset:preset)}}}label:{Label("Speed FX",systemImage:"waveform.path.ecg.rectangle").font(.caption)}
            Button{model.timelineZoom=max(0.35,model.timelineZoom-0.2)}label:{Image(systemName:"minus.magnifyingglass")}
            Button{model.timelineZoom=min(8.0,model.timelineZoom+0.2)}label:{Image(systemName:"plus.magnifyingglass")}
        }.padding(.horizontal,14).foregroundStyle(.secondary)'''
s, count = header_pattern.subn(header_replacement, s, count=1)
if count != 1:
    raise RuntimeError('timeline header not found')

# Replace plain clip cards with real source-frame filmstrips and two-clip selection.
old_card = '''ResizableTimelineClipCardV4(
                    clip:l.clip,
                    index:index,
                    width:w,
                    height:max(40,h-6),
                    selected:l.id==model.selectedClipID,
                    onTap:{model.selectClip(l.id)},
                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{model.moveClip(l.id,translation:$0,pps:pps)}
                )'''
new_card = '''FilmstripClipCardV45(
                    clip:l.clip,
                    index:index,
                    width:CGFloat(w),
                    height:max(40,h-6),
                    selected:l.id==model.selectedClipID,
                    multiSelected:multiSelectedClips.contains(l.id),
                    onTap:{
                        if multiSelectMode {
                            if multiSelectedClips.contains(l.id) { multiSelectedClips.remove(l.id) }
                            else if multiSelectedClips.count < 2 { multiSelectedClips.insert(l.id);model.haptic(.selection) }
                        } else { model.selectClip(l.id) }
                    },
                    onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},
                    onMove:{if !multiSelectMode{model.moveClip(l.id,translation:$0,pps:pps)}}
                )'''
if old_card not in s:
    raise RuntimeError('Resizable clip card not found')
s = s.replace(old_card, new_card, 1)

# Thin trim handles with large invisible hit areas.
s = s.replace('TimelineTrimHandleV4(\n                        leading:true,', 'ThinTrimHandleV45(', 1)
s = s.replace('TimelineTrimHandleV4(\n                        leading:false,', 'ThinTrimHandleV45(', 1)

# Use the smaller direct-touch curve graph.
s = s.replace('CurveEditorGraphV4(model:model,target:target,selectedPointID:$selectedPoint)', 'CurveEditorGraphV45(model:model,target:target,selectedPointID:$selectedPoint)', 1)

# Fit point-mode tabs on narrow iPhones.
picker_pattern = re.compile(r'\s*Picker\("Тип",selection:Binding\(\n\s*get:\{point\.mode\},\n\s*set:\{newMode in model\.setCurvePointMode\(target,pointID:pointID,mode:newMode,resetHandles:newMode == \.smooth\)\}\n\s*\)\) \{\n\s*ForEach\(CurveInterpolation\.allCases\) \{ mode in Text\(mode\.rawValue\)\.tag\(mode\) \}\n\s*\}\n\s*\.pickerStyle\(\.segmented\)', re.S)
picker_replacement = '''
                    CurveModeTabsV45(mode:point.mode){newMode in
                        model.setCurvePointMode(target,pointID:pointID,mode:newMode,resetHandles:newMode == .smooth)
                    }
                    .frame(maxWidth:260)'''
s, count = picker_pattern.subn(picker_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Curve mode segmented picker not found')

# Fast / Smooth speed-processing switch. Smooth is denser remapping, not AI optical flow.
needle = '''            VStack(spacing:4) {
                Slider('''
quality = '''            HStack(spacing:8) {
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
                Slider('''
if needle not in s:
    raise RuntimeError('Curve slider block not found')
s = s.replace(needle, quality, 1)

p.write_text(s)
print('Applied VeloCut v0.4.5 compact UI, filmstrip timeline, merge and smoothing mode')
