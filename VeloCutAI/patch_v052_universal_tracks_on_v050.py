from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# Lane-only patch. Do not replace timelineCanvas, gestures, zoom, playhead or scrolling.
anchor='@Published var audioTimelineStart = 0.0'
if anchor not in s: raise RuntimeError('v0.5 audio state missing')
s=s.replace(anchor,anchor+'\n    @Published var importTargetTrack = 0\n    @Published var audioTrack = 0\n    @Published var audioDurationV52 = 3.0',1)

# Video import respects the lane whose + was used.
old='newClips.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: d, trimStart: 0, trimEnd: d))'
if old not in s: raise RuntimeError('video import anchor missing')
s=s.replace(old,'newClips.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: d, trimStart: 0, trimEnd: d, track: importTargetTrack))',1)

# Keep audio duration for drawing the audio object in a normal lane.
imp='''musicURL = url
        musicName = url.deletingPathExtension().lastPathComponent'''
if imp in s:
    s=s.replace(imp,imp+'''\n        Task { if let d = try? await asset(for:url).load(.duration) { audioDurationV52=max(0.1,CMTimeGetSeconds(d)) } }''',1)

state_pat=re.compile(r'(@State\s+private\s+var\s+multiSelectedClips\s*:\s*Set<UUID>\s*=\s*\[\])')
s,n=state_pat.subn(r'''\1
    @State private var trackNamesV52:[Int:String]=[0:"V1",1:"V2",2:"V3"]
    @State private var trackColorsV52:[Int:Color]=[0:.blue,1:.purple,2:.pink]
    @State private var bypassedTracksV52:Set<Int>=[]
    @State private var audioExtractLaneV52=0
    @State private var extractAudioItemV52:PhotosPickerItem?''',s,count=1)
if n!=1: raise RuntimeError('editor state anchor missing')

# Remove ONLY the separate A1 row from v0.5 workspace.
s=s.replace('timeline;audioLaneV50','timeline')
s=s.replace('timeline.frame(maxHeight:.infinity);audioLaneV50','timeline.frame(maxHeight:.infinity)')

# Make the existing lane title a square; expanding Speed still works on tap.
s=s.replace('Text("V\\(lane+1)")','Text(trackNamesV52[lane] ?? "V\\(lane+1)").lineLimit(1)',1)
s=s.replace('.background(.thinMaterial,in:Capsule())','.frame(width:34,height:28)\n                    .background(trackColorsV52[lane] ?? Color.secondary,in:RoundedRectangle(cornerRadius:7))\n                    .foregroundStyle(.white)',1)

# Reuse the exact existing title position as our safe insertion point.
pos='.position(x:24,y:top+12)'
if pos not in s: raise RuntimeError('lane title position missing')
extra='''.position(x:20,y:top+16)
                .contextMenu{
                    Button("Rename"){trackNamesV52[lane]="Track \\(lane+1)"}
                    Menu("Color"){
                        Button("Blue"){trackColorsV52[lane] = .blue}
                        Button("Purple"){trackColorsV52[lane] = .purple}
                        Button("Pink"){trackColorsV52[lane] = .pink}
                        Button("Green"){trackColorsV52[lane] = .green}
                        Button("Orange"){trackColorsV52[lane] = .orange}
                    }
                }

                Button{
                    if bypassedTracksV52.contains(lane){bypassedTracksV52.remove(lane)}else{bypassedTracksV52.insert(lane)}
                    model.haptic(.selection)
                }label:{Text("B").font(.system(size:9,weight:.bold)).frame(width:24,height:26).background(bypassedTracksV52.contains(lane) ? Color.orange.opacity(0.45):Color.secondary.opacity(0.14),in:RoundedRectangle(cornerRadius:6))}
                .buttonStyle(.plain).position(x:54,y:top+16)

                Menu{
                    PhotosPicker(selection:Binding(get:{[PhotosPickerItem]()},set:{items in model.importTargetTrack=lane;photoItems=items}),maxSelectionCount:20,matching:.videos){Label("Video",systemImage:"film")}
                    PhotosPicker(selection:Binding(get:{extractAudioItemV52},set:{item in audioExtractLaneV52=lane;extractAudioItemV52=item}),matching:.videos){Label("Audio from video",systemImage:"video.badge.waveform")}
                    Button{model.importTargetTrack=lane;model.audioTrack=lane;model.isAudioImporting=true}label:{Label("Audio file",systemImage:"waveform.badge.plus")}
                    Button{model.haptic(.selection)}label:{Label("Photo",systemImage:"photo")}
                    Button{model.haptic(.selection)}label:{Label("FX",systemImage:"sparkles")}
                    Button{model.haptic(.selection)}label:{Label("Text",systemImage:"textformat")}
                    Button{model.haptic(.selection)}label:{Label("Transition",systemImage:"arrow.left.and.right")}
                    Button{model.haptic(.selection)}label:{Label("Speed FX",systemImage:"waveform.path.ecg")}
                }label:{Image(systemName:"plus.circle.fill").font(.system(size:18)).frame(width:28,height:28)}
                .buttonStyle(.plain).position(x:geo.size.width-17,y:top+16)'''
s=s.replace(pos,extra,1)

# Audio is now an object in a normal universal lane, not a separate A1 row.
anchor2='''                if expandedLanes.contains(lane){
                    RoundedRectangle(cornerRadius:7)'''
if anchor2 not in s: raise RuntimeError('lane body anchor missing')
audio='''                if lane == model.audioTrack, let audioName=model.musicName, model.musicURL != nil {
                    let aw=max(52,CGFloat(max(0.1,model.audioDurationV52)*pps))
                    let ax=center+CGFloat((model.audioTimelineStart-model.projectTime)*pps)+aw/2
                    HStack(spacing:4){Image(systemName:"waveform").font(.system(size:8));Text(audioName).font(.system(size:8,weight:.semibold)).lineLimit(1)}
                        .padding(.horizontal,6).frame(width:aw,height:max(28,h-8))
                        .background(Color.cyan.opacity(bypassedTracksV52.contains(lane) ? 0.08:0.22),in:RoundedRectangle(cornerRadius:7))
                        .overlay(RoundedRectangle(cornerRadius:7).stroke(Color.cyan.opacity(0.55),lineWidth:1))
                        .position(x:ax,y:top+h/2)
                        .gesture(DragGesture(minimumDistance:2).onChanged{v in model.audioTimelineStart=max(0,model.audioTimelineStart+Double(v.translation.width)/pps)}.onEnded{_ in model.schedulePreview()})
                }

                if expandedLanes.contains(lane){
                    RoundedRectangle(cornerRadius:7)'''
s=s.replace(anchor2,audio,1)

# Route Audio-file and Audio-from-video imports to the lane that launched them.
sheet_pat=re.compile(r'\.sheet\(isPresented:\s*\$model\.isAudioImporting\)\s*\{\s*AudioPicker\s*\{\s*model\.isAudioImporting\s*=\s*false;\s*model\.importMusic\(\$0\)\s*\}\s*\}')
s,n=sheet_pat.subn('''.sheet(isPresented:$model.isAudioImporting){AudioPicker{model.isAudioImporting=false;model.audioTrack=model.importTargetTrack;model.importMusic($0)}}
        .onChange(of:extractAudioItemV52){_,item in
            guard let item else{return}
            let lane=audioExtractLaneV52
            Task{
                if let movie=try? await item.loadTransferable(type:PickedMovie.self){
                    await MainActor.run{model.audioTrack=lane;model.importTargetTrack=lane}
                    await model.extractAudioFromVideo(movie.url)
                }else{await MainActor.run{model.errorMessage="Не удалось открыть выбранное видео"}}
                await MainActor.run{extractAudioItemV52=nil}
            }
        }''',s,count=1)
if n!=1: raise RuntimeError('audio sheet missing')

p.write_text(s)
print('Applied universal controls inside original v0.5 lanes; A1 removed')
