from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# v0.4.9 audio extraction + beat detector state.
state_anchor = '@Published var musicVolume = 0.8'
if state_anchor not in s:
    raise RuntimeError('musicVolume state not found')
s = s.replace(
    state_anchor,
    state_anchor + '''\n    @Published var isAudioExtracting = false
    @Published var isBeatAnalyzing = false
    @Published var beatMarkers: [VeloCutBeatMarker] = []
    @Published var detectedBPM: Double?
    @Published var beatSensitivity = 0.7
    @Published var snapToBeat = false''',
    1
)

# Upgrade the existing single music track import. Beat analysis is reset whenever
# the source changes so stale markers are never shown for a new song.
old_import = 'func importMusic(_ url: URL) { musicURL = url; musicName = url.deletingPathExtension().lastPathComponent; schedulePreview() }'
new_import = '''func importMusic(_ url: URL) {
        musicURL = url
        musicName = url.deletingPathExtension().lastPathComponent
        beatMarkers = []
        detectedBPM = nil
        schedulePreview()
    }

    func extractAudioFromVideo(_ url: URL) {
        guard !isAudioExtracting else { return }
        isAudioExtracting = true
        Task {
            do {
                let audioURL = try await VeloCutAudioTools.extractAudio(from: url)
                importMusic(audioURL)
                musicName = url.deletingPathExtension().lastPathComponent + " • audio"
                haptic(.medium)
            } catch {
                errorMessage = "Извлечение аудио: \\(error.localizedDescription)"
            }
            isAudioExtracting = false
        }
    }

    func removeMusic() {
        musicURL = nil
        musicName = nil
        beatMarkers = []
        detectedBPM = nil
        snapToBeat = false
        schedulePreview()
    }

    func analyzeMusicBeats() {
        guard let musicURL, !isBeatAnalyzing else {
            if musicURL == nil { errorMessage = "Сначала добавьте аудио" }
            return
        }
        isBeatAnalyzing = true
        beatMarkers = []
        detectedBPM = nil
        let sensitivity = beatSensitivity
        Task {
            do {
                let result = try await VeloCutAudioTools.detectBeats(in: musicURL, sensitivity: sensitivity)
                detectedBPM = result.bpm
                beatMarkers = result.markers
                haptic(.medium)
            } catch {
                errorMessage = "Beat Detector: \\(error.localizedDescription)"
            }
            isBeatAnalyzing = false
        }
    }

    func clearBeatMarkers() {
        beatMarkers = []
        detectedBPM = nil
        snapToBeat = false
    }

    func nearestBeatTime(to time: Double, within tolerance: Double = 0.12) -> Double? {
        guard !beatMarkers.isEmpty else { return nil }
        guard let marker = beatMarkers.min(by: { abs($0.time - time) < abs($1.time - time) }) else { return nil }
        return abs(marker.time - time) <= tolerance ? marker.time : nil
    }

    func seekToPreviousBeat() {
        let target = beatMarkers.map(\\.time).filter { $0 < projectTime - 0.025 }.last ?? beatMarkers.first?.time ?? 0
        seekProject(to: target, exact: true)
        haptic(.selection)
    }

    func seekToNextBeat() {
        let target = beatMarkers.map(\\.time).first(where: { $0 > projectTime + 0.025 }) ?? beatMarkers.last?.time ?? projectTime
        seekProject(to: target, exact: true)
        haptic(.selection)
    }'''
if old_import not in s:
    raise RuntimeError('importMusic method not found')
s = s.replace(old_import, new_import, 1)

# Snap playhead/scrubbing to nearby detected beats, but only inside a small window
# so normal free scrubbing still works naturally.
old_scrub = 'func scrub(to t: Double) { projectTime = min(max(0, t), projectDuration); syncSelectionForProjectTime(); seekProject(to: projectTime, exact: true) }'
new_scrub = '''func scrub(to t: Double) {
        let raw = min(max(0, t), projectDuration)
        projectTime = snapToBeat ? (nearestBeatTime(to: raw, within: 0.11) ?? raw) : raw
        syncSelectionForProjectTime()
        seekProject(to: projectTime, exact: true)
    }'''
if old_scrub not in s:
    raise RuntimeError('scrub method not found')
s = s.replace(old_scrub, new_scrub, 1)

# Add beat marker overlay to the timeline ruler/project area.
timeline_anchor = 'TimelineRulerV4(projectTime:model.projectTime,duration:model.projectDuration,pps:pps).frame(height:rulerH)'
if timeline_anchor not in s:
    raise RuntimeError('timeline ruler anchor not found')
s = s.replace(
    timeline_anchor,
    timeline_anchor + '\n            BeatTimelineMarkersV49(markers:model.beatMarkers,projectTime:model.projectTime,pps:pps,center:center,height:geo.size.height)',
    1
)

# PhotosPicker state dedicated to extracting audio. It does not add the selected
# movie to the video timeline. Match whitespace/format changes from older patches.
s, count = re.subn(
    r'(@State\s+private\s+var\s+speedTab\s*=\s*0)',
    r'\1\n    @State private var extractAudioItem: PhotosPickerItem?',
    s,
    count=1
)
if count != 1:
    raise RuntimeError('InspectorSheet speedTab state not found')

# Replace the compact legacy music panel with explicit import/extract controls,
# beat analysis, BPM display and beat navigation/snap.
audio_pattern = re.compile(r'    private var audio:some View\{.*?\n    private var text:', re.S)
audio_replacement = r'''    private var audio:some View{
        ScrollView(.vertical,showsIndicators:true){
            VStack(spacing:14){
                slider("Громкость клипа",Binding(get:{model.selectedClip?.volume ?? 1},set:{model.setVolume($0)}),0...2)

                VStack(alignment:.leading,spacing:10){
                    HStack{
                        VStack(alignment:.leading,spacing:2){
                            Text("Аудио").font(.headline)
                            Text(model.musicName ?? "Аудиодорожка не добавлена")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        if model.musicURL != nil {
                            Button(role:.destructive){model.removeMusic()}label:{Image(systemName:"trash")}
                                .buttonStyle(.bordered)
                        }
                    }

                    HStack(spacing:8){
                        Button{model.isAudioImporting=true}label:{
                            Label("Из Файлов",systemImage:"waveform.badge.plus")
                                .frame(maxWidth:.infinity)
                        }
                        .buttonStyle(.borderedProminent)

                        PhotosPicker(selection:$extractAudioItem,matching:.videos){
                            Label("Из видео",systemImage:"video.badge.waveform")
                                .frame(maxWidth:.infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                    .onChange(of:extractAudioItem){_,item in
                        guard let item else{return}
                        Task{
                            if let movie=try? await item.loadTransferable(type:PickedMovie.self){
                                await model.extractAudioFromVideo(movie.url)
                            }else{
                                await MainActor.run{model.errorMessage="Не удалось открыть выбранное видео"}
                            }
                            await MainActor.run{extractAudioItem=nil}
                        }
                    }

                    if model.isAudioExtracting {
                        HStack(spacing:8){ProgressView();Text("Извлечение аудио…")}
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if model.musicURL != nil {
                        slider("Громкость аудио",$model.musicVolume,0...1.5)
                    }
                }
                .padding(12)
                .background(.thinMaterial,in:RoundedRectangle(cornerRadius:14))

                if model.musicURL != nil {
                    VStack(alignment:.leading,spacing:11){
                        HStack{
                            VStack(alignment:.leading,spacing:2){
                                Text("Beat Detector").font(.headline)
                                if let bpm=model.detectedBPM {
                                    Text(String(format:"%.1f BPM • %d маркеров",bpm,model.beatMarkers.count))
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }else{
                                    Text("Локальный анализ аудио")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            if model.isBeatAnalyzing { ProgressView().controlSize(.small) }
                        }

                        HStack(spacing:8){
                            Button{model.analyzeMusicBeats()}label:{
                                Label(model.beatMarkers.isEmpty ? "Определить биты":"Пересчитать",systemImage:"metronome")
                                    .frame(maxWidth:.infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(model.isBeatAnalyzing)
                            if !model.beatMarkers.isEmpty {
                                Button{model.clearBeatMarkers()}label:{Image(systemName:"trash")}
                                    .buttonStyle(.bordered)
                            }
                        }

                        VStack(spacing:4){
                            HStack{Text("Чувствительность");Spacer();Text("\(Int(model.beatSensitivity*100))%").monospacedDigit()}
                                .font(.caption)
                            Slider(value:$model.beatSensitivity,in:0.2...1)
                        }

                        if !model.beatMarkers.isEmpty {
                            Toggle("Snap to Beat",isOn:$model.snapToBeat)
                            HStack(spacing:8){
                                Button{model.seekToPreviousBeat()}label:{Label("Пред. бит",systemImage:"backward.end")}
                                    .frame(maxWidth:.infinity)
                                    .buttonStyle(.bordered)
                                Button{model.seekToNextBeat()}label:{Label("След. бит",systemImage:"forward.end")}
                                    .frame(maxWidth:.infinity)
                                    .buttonStyle(.bordered)
                            }
                            Text("Сильные биты отображаются длинными маркерами на таймлайне.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(12)
                    .background(.thinMaterial,in:RoundedRectangle(cornerRadius:14))
                }

                Spacer(minLength:12)
            }
            .padding(.top,8)
            .padding(.bottom,18)
        }
    }
    private var text:'''
s, count = audio_pattern.subn(audio_replacement, s, count=1)
if count != 1:
    raise RuntimeError('Inspector audio block not found')

p.write_text(s)
print('Applied VeloCut v0.4.9 audio import, extraction and beat detector')
