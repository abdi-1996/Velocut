from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# Audio duration state.
anchor='@Published var audioTimelineStart = 0.0'
if anchor not in s: raise RuntimeError('audioTimelineStart missing')
s=s.replace(anchor,anchor+'\n    @Published var audioTimelineDuration = 0.0',1)

# Load duration whenever a new music source is imported.
pat=re.compile(r'(musicURL\s*=\s*url\s*\n\s*musicName\s*=\s*url\.deletingPathExtension\(\)\.lastPathComponent\s*\n\s*audioTimelineStart\s*=\s*projectTime)')
s,count=pat.subn(r'''\1
        Task { [weak self] in
            guard let self else { return }
            let a = AVURLAsset(url:url)
            let d = (try? await a.load(.duration)).map(CMTimeGetSeconds) ?? 0
            await MainActor.run { self.audioTimelineDuration = max(0,d) }
        }''',s,count=1)
if count!=1: raise RuntimeError('audio import duration anchor missing')

# Clear duration when audio is removed.
s=s.replace('musicURL = nil\n        musicName = nil','musicURL = nil\n        musicName = nil\n        audioTimelineDuration = 0',1)

# Remove legacy detached A1 row from workspace.
s=s.replace('timeline;audioLaneV50','timeline')
s=s.replace('VStack(spacing:0){timeline.frame(maxHeight:.infinity);audioLaneV50}','timeline.frame(maxHeight:.infinity)')

# Global track scale must affect every video lane.
s,count=re.subn(r'let laneHeight:\(Int\)->CGFloat=\{laneHeights\[\$0\] \?\? 46\}', 'let laneHeight:(Int)->CGFloat={max(28,(laneHeights[$0] ?? 46)*CGFloat(model.trackHeightScale))}', s, count=1)
if count!=1: raise RuntimeError('laneHeight closure missing')

# Insert synchronized A1 into the same timeline canvas before video clips.
clip_anchor='            ForEach(Array(model.layouts.enumerated()),id:\\.element.id){index,l in'
if clip_anchor not in s: raise RuntimeError('timeline clip anchor missing')
audio_block='''            if let audioName=model.musicName, model.musicURL != nil, model.audioTimelineDuration > 0.01 {
                let audioTop=laneTop(3)
                let audioH:CGFloat=model.collapsedTracks.contains(10) ? 28 : max(32,48*CGFloat(model.trackHeightScale))
                let audioW=max(54,model.audioTimelineDuration*pps)
                let audioX=center+(model.audioTimelineStart-model.projectTime)*pps+audioW/2
                RoundedRectangle(cornerRadius:8)
                    .fill(Color.secondary.opacity(0.045))
                    .frame(height:audioH)
                    .offset(y:audioTop)
                AudioTimelineClipV51(
                    name:audioName,
                    width:audioW,
                    height:max(24,audioH-4),
                    collapsed:model.collapsedTracks.contains(10),
                    onToggleCollapse:{
                        withAnimation(.snappy){
                            if model.collapsedTracks.contains(10){model.collapsedTracks.remove(10)}else{model.collapsedTracks.insert(10)}
                        }
                    },
                    onMove:{dx in
                        model.audioTimelineStart=max(0,min(model.projectDuration,model.audioTimelineStart+Double(dx)/pps))
                        model.schedulePreview()
                    }
                )
                .position(x:audioX,y:audioTop+audioH/2)
            }

'''
s=s.replace(clip_anchor,audio_block+clip_anchor,1)

# Required height uses global scale and includes A1 when present.
old='let video = (0..<3).reduce(CGFloat.zero) { $0 + (laneHeights[$1] ?? 46) }\n        let curves = CGFloat(expandedLanes.count) * 56\n        return max(230,base+video+curves)'
new='let video = (0..<3).reduce(CGFloat.zero) { $0 + max(28,(laneHeights[$1] ?? 46)*CGFloat(model.trackHeightScale)) }\n        let curves = CGFloat(expandedLanes.count) * 56\n        let audio:CGFloat = model.musicURL == nil ? 0 : (model.collapsedTracks.contains(10) ? 28 : max(32,48*CGFloat(model.trackHeightScale)))\n        return max(230,base+video+curves+audio)'
if old not in s: raise RuntimeError('timelineRequiredHeight body missing')
s=s.replace(old,new,1)

# Playback row: time on the left, Play/Pause + Undo + Redo grouped at bottom-right of Preview.
play_pattern=re.compile(r'    private var playback:some View\{.*?\n\n    private var timeline:',re.S)
play_replacement=r'''    private var playback:some View{
        HStack(spacing:8){
            Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))")
                .font(.system(size:10,design:.monospaced))
                .foregroundStyle(.secondary)
            Spacer()
            Button{model.playPause()}label:{
                Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                    .font(.system(size:15,weight:.bold))
                    .frame(width:38,height:28)
                    .background(.thinMaterial,in:Capsule())
            }
            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:30,height:28)}.disabled(!model.canUndo)
            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:30,height:28)}.disabled(!model.canRedo)
        }
        .padding(.horizontal,12)
        .padding(.vertical,5)
        .disabled(model.clips.isEmpty)
    }

    private var timeline:'''
s,count=play_pattern.subn(play_replacement,s,count=1)
if count!=1: raise RuntimeError('playback block missing')

p.write_text(s)
print('Applied VeloCut v0.5.1 timeline audio, global track scaling and preview controls')
