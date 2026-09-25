from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# 1) Restore the ORIGINAL v0.5 per-lane resize engine and connect the global track scale.
# Keep timeline navigation, panning, playhead and pinch zoom unchanged.

# Scale the existing speed sub-lane height without depending on formatting of the timeline constants.
s,n=re.subn(r'curveH\s*=\s*\d+(?:\.\d+)?', 'curveH=56.0*CGFloat(model.trackHeightScale)', s, count=1)
if n!=1:
    raise RuntimeError('curveH geometry missing')

# laneHeight is the original v0.5 source of truth for V1/V2/V3 height.
lane_height_pat=re.compile(r'let\s+laneHeight\s*:\s*\(Int\)\s*->\s*CGFloat\s*=\s*\{\s*laneHeights\[\$0\]\s*\?\?\s*46\s*\}')
s,n=lane_height_pat.subn('let laneHeight:(Int)->CGFloat={(laneHeights[$0] ?? 46)*CGFloat(model.trackHeightScale)}',s,count=1)
if n!=1:
    raise RuntimeError('v0.5 laneHeight closure missing')

# Universal lane header and audio object must use original laneHeight, not fixed 46pt.
fixed='let laneH:CGFloat=46'
if s.count(fixed) < 2:
    raise RuntimeError('universal fixed lane heights missing')
s=s.replace(fixed,'let laneH=laneHeight(lane)',1)
s=s.replace(fixed,'let laneH=laneHeight(a.track)',1)

# Re-add native LaneHeightHandleV4 that was present in v0.5 before the universal header replacement.
chevron='Button{if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}}label:{Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down").font(.system(size:8,weight:.bold)).frame(width:20,height:20).background(.thinMaterial,in:Circle())}.buttonStyle(.plain).position(x:84,y:top+laneH/2)'
if chevron not in s:
    raise RuntimeError('universal lane chevron missing')
resize='''\n                LaneHeightHandleV4(height:laneH){newHeight in
                    laneHeights[lane]=newHeight/max(0.65,CGFloat(model.trackHeightScale))
                }
                .position(x:geo.size.width-44,y:top+laneH-7)'''
s=s.replace(chevron,chevron+resize,1)

# Required vertical scroll height follows individual heights and global scale.
required_pat=re.compile(r'let\s+video\s*=\s*\(0\.\.<3\)\.reduce\(CGFloat\.zero\)\s*\{\s*\$0\s*\+\s*\(laneHeights\[\$1\]\s*\?\?\s*46\)\s*\}\s*\n\s*let\s+curves\s*=\s*CGFloat\(expandedLanes\.count\)\s*\*\s*56')
required_repl='let video = (0..<3).reduce(CGFloat.zero) { $0 + (laneHeights[$1] ?? 46) } * CGFloat(model.trackHeightScale)\n        let curves = CGFloat(expandedLanes.count) * 56 * CGFloat(model.trackHeightScale)'
s,n=required_pat.subn(required_repl,s,count=1)
if n!=1:
    raise RuntimeError('timelineRequiredHeight geometry missing')

# 2) Real rename UI with keyboard/TextField.
state_anchor='@State private var trackNames:[Int:String]=[0:"V1",1:"V2",2:"V3"]'
if state_anchor not in s:
    raise RuntimeError('trackNames state missing')
s=s.replace(state_anchor,state_anchor+'''\n    @State private var renamingLane:Int?\n    @State private var renameTrackText=""\n    @State private var showRenameTrack=false''',1)

old_rename='Button("Переименовать"){trackNames[lane]="Track \\(lane+1)"}'
new_rename='Button("Переименовать"){renamingLane=lane;renameTrackText=trackNames[lane] ?? "V\\(lane+1)";showRenameTrack=true}'
if old_rename not in s:
    raise RuntimeError('rename action missing')
s=s.replace(old_rename,new_rename,1)

body_hook='.onChange(of:photoItems){_,items in loadPhotos(items)}'
if body_hook not in s:
    raise RuntimeError('editor modifier anchor missing')
rename_alert='''.alert("Переименовать дорожку",isPresented:$showRenameTrack){
            TextField("Название дорожки",text:$renameTrackText)
            Button("Отмена",role:.cancel){renamingLane=nil}
            Button("Сохранить"){
                if let lane=renamingLane{
                    let clean=renameTrackText.trimmingCharacters(in:.whitespacesAndNewlines)
                    trackNames[lane]=clean.isEmpty ? "V\\(lane+1)" : String(clean.prefix(18))
                }
                renamingLane=nil
            }
        }'''
s=s.replace(body_hook,body_hook+'\n        '+rename_alert,1)

# 3) Primary audio-track import opens Photos gallery and extracts audio from the selected video.
old_audio_file='Button{pendingAudioLane=lane;model.isAudioImporting=true}label:{Label("Аудиофайл",systemImage:"waveform.badge.plus")}'
old_extract='Button{pendingExtractLane=lane;showTrackExtractPicker=true}label:{Label("Извлечь аудио из видео",systemImage:"video.badge.waveform")}'
if old_audio_file not in s or old_extract not in s:
    raise RuntimeError('audio lane menu anchors missing')
s=s.replace(old_audio_file,'Button{pendingExtractLane=lane;showTrackExtractPicker=true}label:{Label("Аудиодорожка из видео",systemImage:"video.badge.waveform")}',1)
s=s.replace(old_extract,'Button{pendingAudioLane=lane;model.isAudioImporting=true}label:{Label("Аудиофайл из Файлов",systemImage:"waveform.badge.plus")}',1)

# Keep the selected lane until extraction finishes; extracted .m4a becomes TimelineAudioClip in that lane.
old_change='''        .onChange(of:trackExtractItem){_,item in
            guard let item,let lane=pendingExtractLane else{return}
            Task{if let movie=try? await item.loadTransferable(type:PickedMovie.self){await model.extractAudioFromVideo(movie.url,toTrack:lane,at:model.projectTime)}else{await MainActor.run{model.errorMessage="Не удалось открыть видео"}};await MainActor.run{trackExtractItem=nil;pendingExtractLane=nil}}
        }'''
new_change='''        .onChange(of:trackExtractItem){_,item in
            guard let item,let lane=pendingExtractLane else{return}
            Task{
                if let movie=try? await item.loadTransferable(type:PickedMovie.self){
                    await model.extractAudioFromVideo(movie.url,toTrack:lane,at:model.projectTime)
                }else{
                    await MainActor.run{model.errorMessage="Не удалось открыть выбранное видео из галереи"}
                }
                await MainActor.run{trackExtractItem=nil;pendingExtractLane=nil}
            }
        }'''
if old_change not in s:
    raise RuntimeError('audio gallery callback missing')
s=s.replace(old_change,new_change,1)

p.write_text(s)
print('Fixed native lane resizing, editable names, and video-gallery audio extraction')
