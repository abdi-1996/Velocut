from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

anchor='@Published var snapToBeat = false'
if anchor not in s: raise RuntimeError('v049 state missing')
s=s.replace(anchor,anchor+'''\n    @Published var trackHeightScale = 1.0
    @Published var collapsedTracks: Set<Int> = []
    @Published var previewSplit = 0.38
    @Published var workspaceTheme: VeloCutTheme = .iosGlass
    @Published var cacheLimitGB = 5.0
    @Published var audioFadeIn = 0.0
    @Published var audioFadeOut = 0.0
    @Published var audioEffect: VeloCutAudioEffect = .none
    @Published var audioPitch = 0.0
    @Published var audioSpeed = 1.0''',1)

s=s.replace('musicURL = url\n        musicName = url.deletingPathExtension().lastPathComponent', 'musicURL = url\n        musicName = url.deletingPathExtension().lastPathComponent\n        audioTimelineStart = projectTime',1)
music='@Published var musicVolume = 0.8'
if music not in s: raise RuntimeError('music state missing')
s=s.replace(music,music+'\n    @Published var audioTimelineStart = 0.0',1)

method_anchor='    func removeMusic() {'
if method_anchor not in s: raise RuntimeError('removeMusic missing')
methods='''    func setAudioEffect(_ value: VeloCutAudioEffect) { audioEffect=value; schedulePreview() }
    func setAudioPitch(_ value: Double) { audioPitch=min(1200,max(-1200,value)); schedulePreview() }
    func setAudioFadeIn(_ value: Double) { audioFadeIn=max(0,value); schedulePreview() }
    func setAudioFadeOut(_ value: Double) { audioFadeOut=max(0,value); schedulePreview() }

'''
s=s.replace(method_anchor,methods+method_anchor,1)

music_pattern=re.compile(r'''        var musicParams: AVMutableAudioMixInputParameters\?\n        if includeMusic, let musicURL, let musicTrack = composition\.addMutableTrack\(withMediaType: \.audio, preferredTrackID: kCMPersistentTrackID_Invalid\), let src = try await asset\(for: musicURL\)\.loadTracks\(withMediaType: \.audio\)\.first \{\n            let total = CMTimeGetSeconds\(cursor\), musicDuration = CMTimeGetSeconds\(try await asset\(for: musicURL\)\.load\(\.duration\)\), d = min\(total, musicDuration\)\n            if d > 0\.05 \{ try\? musicTrack\.insertTimeRange\(CMTimeRange\(start: \.zero, duration: CMTime\(seconds: d, preferredTimescale: 600\)\), of: src, at: \.zero\); let p = AVMutableAudioMixInputParameters\(track: musicTrack\); p\.setVolume\(Float\(musicVolume\), at: \.zero\); musicParams = p \}\n        \}''')
music_replacement='''        var musicParams: AVMutableAudioMixInputParameters?
        if includeMusic, let musicURL {
            let processedURL = try await VeloCutAudioFX.processedURL(for: musicURL, effect: audioEffect, pitch: audioPitch)
            let processedAsset = asset(for: processedURL)
            if let musicTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid),
               let src = try await processedAsset.loadTracks(withMediaType: .audio).first {
                let total = CMTimeGetSeconds(cursor)
                let start = min(max(0, audioTimelineStart), total)
                let musicDuration = CMTimeGetSeconds(try await processedAsset.load(.duration))
                let d = min(max(0, total-start), musicDuration)
                if d > 0.05 {
                    let at = CMTime(seconds:start, preferredTimescale:600)
                    try? musicTrack.insertTimeRange(CMTimeRange(start:.zero,duration:CMTime(seconds:d,preferredTimescale:600)),of:src,at:at)
                    let params=AVMutableAudioMixInputParameters(track:musicTrack)
                    let level=Float(musicVolume)
                    let fadeIn=min(audioFadeIn,d*0.45), fadeOut=min(audioFadeOut,d*0.45)
                    if fadeIn > 0.01 { params.setVolumeRamp(fromStartVolume:0,toEndVolume:level,timeRange:CMTimeRange(start:at,duration:CMTime(seconds:fadeIn,preferredTimescale:600))) }
                    else { params.setVolume(level,at:at) }
                    if fadeOut > 0.01 {
                        let fadeStart=CMTime(seconds:start+d-fadeOut,preferredTimescale:600)
                        params.setVolumeRamp(fromStartVolume:level,toEndVolume:0,timeRange:CMTimeRange(start:fadeStart,duration:CMTime(seconds:fadeOut,preferredTimescale:600)))
                    }
                    musicParams=params
                }
            }
        }'''
s,count=music_pattern.subn(music_replacement,s,count=1)
if count != 1: raise RuntimeError('music composition block missing')

root_pattern=re.compile(r'ZStack\{Color\(uiColor:\.systemGroupedBackground\)\.ignoresSafeArea\(\);VStack\(spacing:0\)\{preview\.frame\(height:.*?bottomBar\}\.frame\(width:root\.size\.width,height:root\.size\.height,alignment:\.top\)\}',re.S)
s,count=root_pattern.subn('ZStack{model.workspaceTheme.background.ignoresSafeArea();adaptiveWorkspace(root)}',s,count=1)
if count != 1: raise RuntimeError('Editor root ZStack not found')

# Appearance state and sheet use structural matchers because older UI patches reformat state declarations.
s,count=re.subn(r'(@State\s+private\s+var\s+showShare\s*=\s*false)',r'\1\n    @State private var showAppearanceV50=false',s,count=1)
if count != 1: raise RuntimeError('showShare state missing')
s,count=re.subn(r'(\.sheet\(isPresented:\s*\$model\.isAudioImporting\)\s*\{\s*AudioPicker\s*\{\s*model\.isAudioImporting\s*=\s*false;\s*model\.importMusic\(\$0\)\s*\}\s*\})',r'\1\n        .sheet(isPresented:$showAppearanceV50){VeloCutThemeSettingsV50(model:model)}',s,count=1)
if count != 1: raise RuntimeError('audio sheet missing')

mark='    private var topBar:some View'
if mark not in s: raise RuntimeError('topbar declaration missing')
insert='''    @ViewBuilder private func adaptiveWorkspace(_ root: GeometryProxy)->some View {
        let landscape = root.size.width > root.size.height
        if landscape {
            VStack(spacing:0){
                HStack(spacing:0){
                    VStack(spacing:0){preview;playback}.frame(width:root.size.width*0.46)
                    Divider()
                    VStack(spacing:0){workspaceHandle;if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil})}else{timeline;audioLaneV50}}.frame(maxWidth:.infinity)
                }
                bottomBar
            }
        } else {
            VStack(spacing:0){preview.frame(height:max(150,root.size.height*model.previewSplit));playback;workspaceHandle;if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{VStack(spacing:0){timeline.frame(maxHeight:.infinity);audioLaneV50}};bottomBar}
        }
    }

    private var workspaceHandle: some View {
        Capsule().fill(Color.secondary.opacity(0.45)).frame(width:46,height:5).frame(height:18).contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance:0).onChanged{v in let delta=Double(v.translation.height/700);model.previewSplit=min(0.62,max(0.22,model.previewSplit+delta))}.onEnded{_ in model.haptic(.selection)})
    }

'''
s=s.replace(mark,insert+mark,1)

menu_anchor='Button{model.isFileImporting=true}label:{Label("Импорт из Файлов",systemImage:"folder")}'
if menu_anchor in s:s=s.replace(menu_anchor,menu_anchor+'\n                            Button{showAppearanceV50=true}label:{Label("Appearance & Cache",systemImage:"paintpalette")}',1)
else: raise RuntimeError('clean preview menu missing')

header='Label("Таймлайн",systemImage:"timeline.selection")'
if header not in s: raise RuntimeError('timeline header missing')
s=s.replace(header,'Label("Таймлайн",systemImage:"timeline.selection");Button{withAnimation(.snappy){if model.collapsedTracks.contains(0){model.collapsedTracks.remove(0)}else{model.collapsedTracks.insert(0)}}}label:{Image(systemName:model.collapsedTracks.contains(0) ? "chevron.right":"chevron.down")};Slider(value:$model.trackHeightScale,in:0.65...1.8).frame(width:92)',1)

audio_volume='slider("Громкость аудио",$model.musicVolume,0...1.5)'
if audio_volume in s:
    controls=r'''
                        Picker("Эффект",selection:Binding(get:{model.audioEffect},set:{model.setAudioEffect($0)})){ForEach(VeloCutAudioEffect.allCases){Text($0.rawValue).tag($0)}}.pickerStyle(.menu)
                        HStack{Text("Pitch").font(.caption);Slider(value:Binding(get:{model.audioPitch},set:{model.setAudioPitch($0)}),in:-1200...1200,step:25);Text("\(Int(model.audioPitch))").font(.caption.monospacedDigit())}
                        HStack{Text("Fade In").font(.caption);Slider(value:Binding(get:{model.audioFadeIn},set:{model.setAudioFadeIn($0)}),in:0...5)}
                        HStack{Text("Fade Out").font(.caption);Slider(value:Binding(get:{model.audioFadeOut},set:{model.setAudioFadeOut($0)}),in:0...5)}'''
    s=s.replace(audio_volume,audio_volume+controls,1)
else: raise RuntimeError('audio volume control missing')

mark='    private var bottomBar:'
extra='''    private var audioLaneV50: some View {
        Group{if let name=model.musicName,model.musicURL != nil{HStack(spacing:8){Button{withAnimation(.snappy){if model.collapsedTracks.contains(10){model.collapsedTracks.remove(10)}else{model.collapsedTracks.insert(10)}}}label:{Image(systemName:model.collapsedTracks.contains(10) ? "chevron.right":"chevron.down")};Text("A1").font(.caption.bold());Image(systemName:"waveform");Text(name).font(.caption).lineLimit(1);Spacer();Text(String(format:"%.1fs",model.audioTimelineStart)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)}.padding(.horizontal,10).frame(height:model.collapsedTracks.contains(10) ? 28:CGFloat(48*model.trackHeightScale)).background(model.workspaceTheme.panel.opacity(0.92),in:RoundedRectangle(cornerRadius:9)).padding(.horizontal,10).padding(.bottom,5).gesture(DragGesture().onEnded{v in model.audioTimelineStart=max(0,min(model.projectDuration,model.audioTimelineStart+Double(v.translation.width/max(24,34*model.timelineZoom))));model.schedulePreview()})}}
    }

'''
s=s.replace(mark,extra+mark,1)

old_end='onEnded{_ in timelineDragStart=nil;model.endScrub()}'
if old_end in s:s=s.replace(old_end,'onEnded{v in let base=timelineDragStart ?? model.projectTime;let extra=Double(v.predictedEndTranslation.width-v.translation.width)/pps;timelineDragStart=nil;model.endScrub();withAnimation(.easeOut(duration:0.32)){model.scrub(to:base-Double(v.translation.width)/pps-extra*0.72);model.endScrub()}}',1)

p.write_text(s)
print('Applied VeloCut v0.5.0 pro workspace, audio FX, themes and inertia')
