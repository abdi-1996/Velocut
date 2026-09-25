from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

state='@Published var audioTimelineStart = 0.0'
if state not in s: raise RuntimeError('audioTimelineStart missing')
s=s.replace(state,state+'\n    @Published var audioDuration = 0.0',1)

needle='audioTimelineStart = projectTime\n        beatMarkers = []'
if needle not in s:
    s,count=re.subn(r'(musicName\s*=\s*url\.deletingPathExtension\(\)\.lastPathComponent\n\s*audioTimelineStart\s*=\s*projectTime)',r'''\1
        Task {
            if let d = try? await asset(for:url).load(.duration) {
                audioDuration = max(0.05, CMTimeGetSeconds(d))
            }
        }''',s,count=1)
    if count!=1: raise RuntimeError('importMusic duration anchor missing')
else:
    s=s.replace(needle,'''audioTimelineStart = projectTime
        Task {
            if let d = try? await asset(for:url).load(.duration) {
                audioDuration = max(0.05, CMTimeGetSeconds(d))
            }
        }
        beatMarkers = []''',1)

s,count=re.subn(r'(func removeMusic\(\) \{\n\s*musicURL = nil\n\s*musicName = nil)',r'''\1
        audioDuration = 0
        audioTimelineStart = 0''',s,count=1)
if count!=1: raise RuntimeError('removeMusic reset anchor missing')

lane_pattern=re.compile(r'let\s+laneHeight\s*:\s*\(Int\)\s*->\s*CGFloat\s*=\s*\{.*?\}',re.S)
lane_repl='let laneHeight:(Int)->CGFloat={lane in model.collapsedTracks.contains(lane) ? 28 : max(32,(laneHeights[lane] ?? 46)*CGFloat(model.trackHeightScale))}'
s,count=lane_pattern.subn(lane_repl,s,count=1)
if count!=1: raise RuntimeError('laneHeight closure missing')

s,count=re.subn(r'let\s+pps\s*=\s*34\.0\s*\*\s*model\.timelineZoom\s*,\s*center\s*=\s*geo\.size\.width/2\s*,\s*rulerH\s*=\s*22\.0\s*,\s*fxH\s*=\s*[^,\n]+\s*,\s*curveH\s*=\s*[^\n]+',
'''let pps=34.0*model.timelineZoom, center=geo.size.width/2, rulerH=22.0, fxH=max(30,42.0*CGFloat(model.trackHeightScale)), curveH=max(34,56.0*CGFloat(model.trackHeightScale))''',s,count=1)
if count!=1: raise RuntimeError('timeline constants missing')

height_pattern=re.compile(r'    private var timelineRequiredHeight\s*:\s*CGFloat\s*\{.*?\n    \}',re.S)
height_repl='''    private var timelineRequiredHeight:CGFloat {
        let scale=CGFloat(model.trackHeightScale)
        let base:CGFloat = 22 + max(30,42*scale) + 12
        let video=(0..<3).reduce(CGFloat.zero){sum,lane in sum + (model.collapsedTracks.contains(lane) ? 28 : max(32,(laneHeights[lane] ?? 46)*scale))}
        let expandedCount=(0..<3).filter{expandedLanes.contains($0) && !model.collapsedTracks.contains($0)}.count
        let curves=CGFloat(expandedCount)*max(34,56*scale)
        return max(230,base+video+curves)
    }'''
s,count=height_pattern.subn(height_repl,s,count=1)
if count!=1: raise RuntimeError('timelineRequiredHeight block missing')

s=s.replace('else{timeline;audioLaneV50}', 'else{timeline}',1)
s=s.replace('else{VStack(spacing:0){timeline.frame(maxHeight:.infinity);audioLaneV50}}', 'else{timeline.frame(maxHeight:.infinity)}',1)

canvas_pattern=re.compile(r'ScrollView\(\.vertical,showsIndicators:false\)\{GeometryReader\{geo in timelineCanvas\(geo\)\}\.frame\(height:timelineRequiredHeight\)\}\.frame\(minHeight:230,maxHeight:360\)')
s,count=canvas_pattern.subn('''VStack(spacing:4){
            ScrollView(.vertical,showsIndicators:false){GeometryReader{geo in timelineCanvas(geo)}.frame(height:timelineRequiredHeight)}.frame(minHeight:180,maxHeight:360)
            audioLaneV50
        }''',s,count=1)
if count!=1: raise RuntimeError('timeline scroll row missing')

audio_pattern=re.compile(r'    private var audioLaneV50: some View \{.*?\n    \}\n\n    private var bottomBar:',re.S)
audio_repl=r'''    private var audioLaneV50: some View {
        GeometryReader{geo in
            let pps=34.0*model.timelineZoom
            let center=geo.size.width/2
            let h:CGFloat=model.collapsedTracks.contains(10) ? 28 : max(34,48*CGFloat(model.trackHeightScale))
            ZStack(alignment:.topLeading){
                RoundedRectangle(cornerRadius:9).fill(Color.secondary.opacity(0.055))
                HStack(spacing:5){
                    Button{withAnimation(.snappy){if model.collapsedTracks.contains(10){model.collapsedTracks.remove(10)}else{model.collapsedTracks.insert(10)}}}label:{Image(systemName:model.collapsedTracks.contains(10) ? "chevron.right":"chevron.down")}
                    Text("A1").font(.system(size:9,weight:.bold))
                }.padding(.leading,6).frame(height:h)
                if let name=model.musicName,model.musicURL != nil {
                    let duration=max(0.1,model.audioDuration)
                    let width=max(54,CGFloat(duration*pps))
                    let x=center+CGFloat((model.audioTimelineStart-model.projectTime)*pps)+width/2
                    HStack(spacing:6){
                        Image(systemName:"waveform").font(.caption)
                        Text(name).font(.caption2.weight(.semibold)).lineLimit(1)
                        Spacer(minLength:2)
                        Text(String(format:"%.1fs",duration)).font(.system(size:8,design:.monospaced)).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal,8)
                    .frame(width:width,height:max(24,h-6))
                    .background(Color.accentColor.opacity(0.18),in:RoundedRectangle(cornerRadius:7))
                    .overlay(RoundedRectangle(cornerRadius:7).stroke(Color.accentColor.opacity(0.55),lineWidth:1))
                    .position(x:x,y:h/2)
                    .gesture(DragGesture(minimumDistance:2).onChanged{v in
                        let newStart=model.audioTimelineStart+Double(v.translation.width)/pps
                        model.audioTimelineStart=max(0,min(max(0,model.projectDuration-0.02),newStart))
                    }.onEnded{_ in model.schedulePreview()})
                } else {
                    Text("Импортируйте аудио").font(.caption2).foregroundStyle(.secondary).position(x:center,y:h/2)
                }
                Rectangle().fill(Color.red.opacity(0.85)).frame(width:1.2,height:h).position(x:center,y:h/2)
            }.clipped()
        }
        .frame(height:model.collapsedTracks.contains(10) ? 28:max(34,48*CGFloat(model.trackHeightScale)))
        .padding(.horizontal,8)
    }

    private var bottomBar:'''
s,count=audio_pattern.subn(audio_repl,s,count=1)
if count!=1: raise RuntimeError('audioLaneV50 block missing')

play_pattern=re.compile(r'    private var playback\s*:\s*some View\s*\{.*?\n\n    private var timeline:',re.S)
play_repl=r'''    private var playback:some View{
        HStack(spacing:8){
            Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))")
                .font(.system(size:10,design:.monospaced)).foregroundStyle(.secondary)
            Spacer()
            Button{model.playPause()}label:{Image(systemName:model.isPlaying ? "pause.fill":"play.fill").font(.system(size:15,weight:.bold)).frame(width:38,height:30).background(.thinMaterial,in:Capsule())}
            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:30,height:30)}.disabled(!model.canUndo)
            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:30,height:30)}.disabled(!model.canRedo)
        }
        .padding(.horizontal,12).padding(.vertical,5)
        .disabled(model.clips.isEmpty)
    }

    private var timeline:'''
s,count=play_pattern.subn(play_repl,s,count=1)
if count!=1: raise RuntimeError('playback block missing')

p.write_text(s)
print('Applied v0.5.0 A1 timeline lane, working track scale, and right-side playback controls')
