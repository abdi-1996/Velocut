from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# VeloCut v0.6.0 — grouped main tracks (Video / Audio / Text / FX)
# Preserve the existing v0.5.x timeline engine and layer this workflow on top.

# 1) Group UI state.
state_anchor='@State private var audioDragPreview: [UUID: CGSize] = [:]'
if state_anchor not in s:
    raise RuntimeError('v0.5.9 audioDragPreview state missing')
state_extra='''
    @State private var videoGroupExpanded = true
    @State private var audioGroupExpanded = false
    @State private var textGroupExpanded = false
    @State private var fxGroupExpanded = false
    @State private var videoSubtrackCount = 0
    @State private var audioSubtrackCount = 0
    @State private var textSubtrackCount = 0
    @State private var fxSubtrackCount = 0
    @State private var showAudioSourceMenu = false
    @State private var trackColorIndex: [Int:Int] = [:]
'''
s=s.replace(state_anchor,state_anchor+state_extra,1)

# Maximum 10 video subtracks.
old_add='''    func addTrack() {
        trackCount += 1
        haptic(.selection)
    }'''
new_add='''    func addTrack() {
        guard trackCount < 10 else { haptic(.error); return }
        trackCount += 1
        haptic(.selection)
    }'''
if old_add not in s:
    raise RuntimeError('addTrack method missing')
s=s.replace(old_add,new_add,1)

# 2) Helpers for colors and automatic subtrack creation.
helper_anchor='    private var playback:some View{'
if helper_anchor not in s:
    raise RuntimeError('playback anchor missing')
helpers=r'''    private func v060TrackColor(_ lane:Int)->Color {
        switch trackColorIndex[lane] ?? 0 {
        case 1: return .blue
        case 2: return .red
        case 3: return .purple
        case 4: return .green
        case 5: return .orange
        default: return Color.primary.opacity(0.10)
        }
    }

    private func v060CycleTrackColor(_ lane:Int) {
        trackColorIndex[lane]=((trackColorIndex[lane] ?? 0)+1)%6
        model.haptic(.selection)
    }

    private var v060UsedVideoSubtracks:Int {
        let used=(model.clips.map{$0.track}.max() ?? -1)+1
        return min(10,max(videoSubtrackCount,used))
    }

    private func v060AddVideoMedia() {
        if videoSubtrackCount == 0 { videoSubtrackCount=1 }
        let lane=min(9,max(0,v060UsedVideoSubtracks-1))
        if model.trackCount <= lane { while model.trackCount <= lane && model.trackCount < 10 { model.addTrack() } }
        pendingMediaLane=lane
        showTrackMediaPicker=true
        videoGroupExpanded=true
    }

    private func v060AddAudio() {
        if audioSubtrackCount == 0 { audioSubtrackCount=1 }
        audioGroupExpanded=true
        showAudioSourceMenu=true
    }

    private func v060AddText() {
        if textSubtrackCount == 0 { textSubtrackCount=1 }
        textGroupExpanded=true
        inspector = .text
        model.haptic(.selection)
    }

    private func v060AddFX() {
        if fxSubtrackCount == 0 { fxSubtrackCount=1 }
        fxGroupExpanded=true
        inspector = .filters
        model.haptic(.selection)
    }

'''
s=s.replace(helper_anchor,helpers+helper_anchor,1)

# 3) Audio main-track + offers Files or Gallery video extraction.
modifier_anchor='.alert("Переименовать дорожку",isPresented:$showRenameTrack){'
if modifier_anchor not in s:
    raise RuntimeError('rename alert modifier missing')
audio_dialog=r'''.confirmationDialog("Добавить аудио",isPresented:$showAudioSourceMenu,titleVisibility:.visible){
            Button("Аудио из Файлов"){
                pendingAudioLane=0
                model.isAudioImporting=true
            }
            Button("Извлечь из видео в Галерее"){
                pendingExtractLane=0
                showTrackExtractPicker=true
            }
            Button("Отмена",role:.cancel){}
        }
        '''
s=s.replace(modifier_anchor,audio_dialog+modifier_anchor,1)

# 4) Expand the unified left rail and add the four main track headers.
old_frame='.frame(width:118,height:max(36,railBottom-railTop))'
new_frame='.frame(width:118,height:max(172,railBottom-railTop+136))'
if old_frame not in s:
    raise RuntimeError('v0.5.9 unified rail frame missing')
s=s.replace(old_frame,new_frame,1)

controls_anchor='''            ForEach(0..<model.trackCount,id:\\.self){lane in
                let top=laneTop(lane),laneH=laneHeight(lane),panelW:CGFloat=118'''
if controls_anchor not in s:
    raise RuntimeError('v0.5.9 controls anchor missing')
group_headers=r'''            // Main grouped tracks. Their + buttons perform the primary action and
            // automatically create the first subtrack when the group is empty.
            HStack(spacing:4){
                Image(systemName:"photo.on.rectangle").frame(width:18)
                Text("Video").font(.system(size:10,weight:.semibold)).lineLimit(1)
                Spacer(minLength:1)
                Button{model.toggleTrackMute(0)}label:{Text("M").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{}label:{Text("S").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{v060AddVideoMedia()}label:{Image(systemName:"plus").font(.system(size:10,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.90),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{withAnimation(.snappy){videoGroupExpanded.toggle()}}label:{Image(systemName:videoGroupExpanded ? "triangle.fill":"triangle.fill").rotationEffect(.degrees(videoGroupExpanded ? 180:90)).font(.system(size:8)).frame(width:16,height:20)}.buttonStyle(.plain)
            }
            .padding(.horizontal,7).frame(width:118,height:30)
            .background(Color.black.opacity(0.20),in:RoundedRectangle(cornerRadius:8))
            .position(x:59,y:max(16,railTop-16)).zIndex(110)

            HStack(spacing:4){
                Image(systemName:"music.note").frame(width:18)
                Text("Audio").font(.system(size:10,weight:.semibold));Spacer(minLength:1)
                Text("M").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Text("S").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Button{v060AddAudio()}label:{Image(systemName:"plus").font(.system(size:10,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.90),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{withAnimation(.snappy){audioGroupExpanded.toggle()}}label:{Image(systemName:"triangle.fill").rotationEffect(.degrees(audioGroupExpanded ? 180:90)).font(.system(size:8)).frame(width:16,height:20)}.buttonStyle(.plain)
            }.padding(.horizontal,7).frame(width:118,height:30).background(Color.black.opacity(0.20),in:RoundedRectangle(cornerRadius:8)).position(x:59,y:railBottom+18).zIndex(110)

            HStack(spacing:4){
                Image(systemName:"textformat").frame(width:18)
                Text("Text").font(.system(size:10,weight:.semibold));Spacer(minLength:1)
                Text("M").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Text("S").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Button{v060AddText()}label:{Image(systemName:"plus").font(.system(size:10,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.90),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{withAnimation(.snappy){textGroupExpanded.toggle()}}label:{Image(systemName:"triangle.fill").rotationEffect(.degrees(textGroupExpanded ? 180:90)).font(.system(size:8)).frame(width:16,height:20)}.buttonStyle(.plain)
            }.padding(.horizontal,7).frame(width:118,height:30).background(Color.black.opacity(0.20),in:RoundedRectangle(cornerRadius:8)).position(x:59,y:railBottom+52).zIndex(110)

            HStack(spacing:4){
                Text("Fx").font(.system(size:14,weight:.medium)).frame(width:18)
                Text("FX").font(.system(size:10,weight:.semibold));Spacer(minLength:1)
                Text("M").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Text("S").font(.system(size:9,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.86),in:Circle()).foregroundStyle(.black)
                Button{v060AddFX()}label:{Image(systemName:"plus").font(.system(size:10,weight:.bold)).frame(width:19,height:19).background(Color.white.opacity(0.90),in:Circle()).foregroundStyle(.black)}.buttonStyle(.plain)
                Button{withAnimation(.snappy){fxGroupExpanded.toggle()}}label:{Image(systemName:"triangle.fill").rotationEffect(.degrees(fxGroupExpanded ? 180:90)).font(.system(size:8)).frame(width:16,height:20)}.buttonStyle(.plain)
            }.padding(.horizontal,7).frame(width:118,height:30).background(Color.black.opacity(0.20),in:RoundedRectangle(cornerRadius:8)).position(x:59,y:railBottom+86).zIndex(110)

'''
s=s.replace(controls_anchor,group_headers+controls_anchor,1)

# 5) Existing generic lanes now visually act as Video subtracks only.
# Hide unused lanes on a clean project and when Video is collapsed.
position_anchor='''.position(x:59,y:top+laneH/2)
                .zIndex(40)'''
position_repl='''.position(x:59,y:top+laneH/2)
                .opacity(videoGroupExpanded && lane < v060UsedVideoSubtracks ? 1 : 0)
                .allowsHitTesting(videoGroupExpanded && lane < v060UsedVideoSubtracks)
                .zIndex(40)'''
if position_anchor not in s:
    raise RuntimeError('per-lane control position missing')
s=s.replace(position_anchor,position_repl,1)

# Color square before each video subtrack name. Tap cycles standard colors.
menu_anchor='''                    HStack(spacing:3){
                        Menu{
                            Button("Переименовать")'''
if menu_anchor not in s:
    # v0.5.8 may have spacing:2 depending on the first HStack matcher
    menu_anchor='''                    HStack(spacing:2){
                        Menu{
                            Button("Переименовать")'''
if menu_anchor not in s:
    raise RuntimeError('track controls HStack/menu missing')
spacing='3' if 'HStack(spacing:3)' in menu_anchor else '2'
menu_repl=f'''                    HStack(spacing:{spacing}){{
                        Button{{v060CycleTrackColor(lane)}}label:{{
                            RoundedRectangle(cornerRadius:3).fill(v060TrackColor(lane)).frame(width:12,height:22)
                        }}.buttonStyle(.plain)
                        Menu{{
                            Button("Переименовать")'''
s=s.replace(menu_anchor,menu_repl,1)

# 6) Keep enough vertical scroll room for grouped main rows beneath video lanes.
height_anchor='''        let base:CGFloat = 22 + 12'''
if height_anchor in s:
    s=s.replace(height_anchor,'        let base:CGFloat = 22 + 12 + 136',1)
else:
    # fallback: add to the return line if compact patches changed formatting
    s,n=re.subn(r'(private var timelineRequiredHeight:CGFloat \{.*?return\s+)([^\n]+)',lambda m:m.group(1)+'('+m.group(2)+') + 136',s,count=1,flags=re.S)
    if n!=1: raise RuntimeError('timelineRequiredHeight expansion missing')

p.write_text(s)
print('Applied VeloCut v0.6.0 grouped Video/Audio/Text/FX main-track workflow')
