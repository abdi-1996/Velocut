from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# VeloCut v0.5.5: keep v0.5 timeline/navigation engine, upgrade track shell only.

state_anchor='@Published var bypassedTracks: Set<Int> = []'
if state_anchor not in s:
    raise RuntimeError('bypassedTracks state missing')
s=s.replace(state_anchor, state_anchor+'''\n    @Published var mutedTracks: Set<Int> = []\n    @Published var trackCount: Int = 3\n    @Published var selectedAudioClipID: UUID?''', 1)

audio_fields='''    var track: Int\n    var volume: Double\n    init(id: UUID = UUID(), url: URL, name: String, duration: Double, start: Double, track: Int, volume: Double = 1) {\n        self.id=id; self.url=url; self.name=name; self.duration=duration; self.start=start; self.track=track; self.volume=volume\n    }'''
audio_fields_new='''    var track: Int\n    var volume: Double\n    var sourceStart: Double\n    init(id: UUID = UUID(), url: URL, name: String, duration: Double, start: Double, track: Int, volume: Double = 1, sourceStart: Double = 0) {\n        self.id=id; self.url=url; self.name=name; self.duration=duration; self.start=start; self.track=track; self.volume=volume; self.sourceStart=sourceStart\n    }'''
if audio_fields not in s:
    raise RuntimeError('TimelineAudioClip fields missing')
s=s.replace(audio_fields,audio_fields_new,1)

old_duration='var projectDuration: Double { layouts.last?.end ?? 0 }'
if old_duration not in s:
    raise RuntimeError('projectDuration missing')
s=s.replace(old_duration,'var projectDuration: Double { max(layouts.last?.end ?? 0, audioClips.map(\\.end).max() ?? 0) }',1)

s=s.replace('track: min(2,max(0,targetTrack ?? 0))','track: max(0,targetTrack ?? 0)')
s=s.replace('track:min(2,max(0,track))','track:max(0,track)')
s=s.replace('audioClips[i].track=min(2,max(0,original.track+laneDelta))','audioClips[i].track=min(max(0,trackCount-1),max(0,original.track+laneDelta))')
s=s.replace('c.track = min(2, max(0, c.track + vertical))','c.track = min(max(0, trackCount-1), max(0, c.track + vertical))')

method_anchor='    func toggleTrackBypass(_ lane:Int){'
idx=s.find(method_anchor)
if idx<0:
    raise RuntimeError('toggleTrackBypass missing')
end=s.find('\n',idx)
if end<0:
    raise RuntimeError('toggleTrackBypass line end missing')
extra_methods=r'''
    func addTrack() {
        trackCount += 1
        haptic(.selection)
    }

    func toggleTrackMute(_ lane:Int) {
        if mutedTracks.contains(lane){mutedTracks.remove(lane)}else{mutedTracks.insert(lane)}
        schedulePreview(immediate:true)
    }

    var selectedAudioClip: TimelineAudioClip? {
        guard let id=selectedAudioClipID else{return nil}
        return audioClips.first(where:{$0.id==id})
    }

    func selectAudioClip(_ id:UUID) {
        selectedAudioClipID=id
        selectedClipID=nil
        haptic(.selection)
    }

    func setSelectedAudioVolume(_ value:Double) {
        guard let id=selectedAudioClipID,let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        audioClips[i].volume=min(2,max(0,value))
        schedulePreview()
    }

    func splitSelectedAudioAtPlayhead() {
        guard let id=selectedAudioClipID,let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let item=audioClips[i]
        let local=projectTime-item.start
        guard local>0.05,local<item.duration-0.05 else{haptic(.error);return}
        registerUndo()
        audioClips[i].duration=local
        let right=TimelineAudioClip(url:item.url,name:item.name,duration:item.duration-local,start:projectTime,track:item.track,volume:item.volume,sourceStart:item.sourceStart+local)
        audioClips.insert(right,at:i+1)
        selectedAudioClipID=right.id
        schedulePreview(immediate:true)
        haptic(.medium)
    }

    func trimSelectedAudioStartToPlayhead() {
        guard let id=selectedAudioClipID,let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let item=audioClips[i],cut=projectTime-item.start
        guard cut>0.02,cut<item.duration-0.02 else{haptic(.error);return}
        registerUndo()
        audioClips[i].sourceStart += cut
        audioClips[i].start=projectTime
        audioClips[i].duration -= cut
        schedulePreview(immediate:true)
    }

    func trimSelectedAudioEndToPlayhead() {
        guard let id=selectedAudioClipID,let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let item=audioClips[i],newDuration=projectTime-item.start
        guard newDuration>0.02,newDuration<item.duration-0.02 else{haptic(.error);return}
        registerUndo()
        audioClips[i].duration=newDuration
        schedulePreview(immediate:true)
    }

    func duplicateSelectedAudio() {
        guard let id=selectedAudioClipID,let item=audioClips.first(where:{$0.id==id}) else{return}
        registerUndo()
        let copy=TimelineAudioClip(url:item.url,name:item.name+" copy",duration:item.duration,start:item.end,track:item.track,volume:item.volume,sourceStart:item.sourceStart)
        audioClips.append(copy)
        selectedAudioClipID=copy.id
        schedulePreview(immediate:true)
    }

    func deleteSelectedAudio() {
        guard let id=selectedAudioClipID else{return}
        registerUndo()
        audioClips.removeAll{$0.id==id}
        selectedAudioClipID=nil
        schedulePreview(immediate:true)
    }
'''
s=s[:end+1]+extra_methods+s[end+1:]

old_select='func selectClip(_ id: UUID, seek: Bool = true) { selectedClipID = id; if seek { seekProject(to: projectStart(of: id), exact: true) } }'
if old_select in s:
    s=s.replace(old_select,'func selectClip(_ id: UUID, seek: Bool = true) { selectedAudioClipID=nil; selectedClipID = id; if seek { seekProject(to: projectStart(of: id), exact: true) } }',1)
else:
    raise RuntimeError('selectClip missing')

pat_import=re.compile(r'audioClips\.append\(TimelineAudioClip\(url:url,name:url\.deletingPathExtension\(\)\.lastPathComponent,duration:d,start:max\(0,time \?\? projectTime\),track:max\(0,track\)\)\)')
s,n=pat_import.subn('let newAudio=TimelineAudioClip(url:url,name:url.deletingPathExtension().lastPathComponent,duration:d,start:max(0,time ?? projectTime),track:max(0,track)); audioClips.append(newAudio); selectedAudioClipID=newAudio.id; selectedClipID=nil',s,count=1)
if n!=1:
    raise RuntimeError('audio file import append missing')

pat_extract=re.compile(r'audioClips\.append\(TimelineAudioClip\(url:u,name:url\.deletingPathExtension\(\)\.lastPathComponent\+" • audio",duration:d,start:max\(0,time \?\? projectTime\),track:max\(0,track\)\)\)')
s,n=pat_extract.subn('let newAudio=TimelineAudioClip(url:u,name:url.deletingPathExtension().lastPathComponent+" • audio",duration:d,start:max(0,time ?? projectTime),track:max(0,track)); audioClips.append(newAudio); selectedAudioClipID=newAudio.id; selectedClipID=nil',s,count=1)
if n!=1:
    raise RuntimeError('extracted audio append missing')

vol='audioParams?.setVolume(Float(clip.volume), at: cursor)'
if vol not in s:
    raise RuntimeError('video clip audio volume anchor missing')
s=s.replace(vol,'audioParams?.setVolume(Float(mutedTracks.contains(clip.track) ? 0 : clip.volume), at: cursor)',1)

lane_loop='for item in audioClips where !bypassedTracks.contains(item.track) {'
if lane_loop not in s:
    raise RuntimeError('lane audio composition loop missing')
s=s.replace(lane_loop,'for item in audioClips where !bypassedTracks.contains(item.track) && !mutedTracks.contains(item.track) {',1)
old_range='let range=CMTimeRange(start:.zero,duration:CMTime(seconds:maxD,preferredTimescale:600))'
if old_range not in s:
    raise RuntimeError('lane audio range missing')
s=s.replace(old_range,'let range=CMTimeRange(start:CMTime(seconds:item.sourceStart,preferredTimescale:600),duration:CMTime(seconds:maxD,preferredTimescale:600))',1)

s,n=re.subn(r'fxH\s*=\s*42(?:\.0)?', 'fxH=0.0', s, count=1)
if n!=1:
    raise RuntimeError('fxH missing')

# Hide the old FX strip defensively; earlier UI patches may reformat this line.
s=s.replace('.frame(height:fxH-3)', '.frame(height:0)', 1)
s=s.replace('Text("FX")', 'Text("")', 1)

speed_block_pat=re.compile(r'\s*ForEach\(model\.speedFX\)\{fx in.*?(?=\s*ForEach\(0\.\.<3,id:\\\.self\)\{lane in)',re.S)
s,n=speed_block_pat.subn('\n',s,count=1)
if n!=1:
    raise RuntimeError('top SpeedFX block group missing')

lane_group_pat=re.compile(r'ForEach\(0\.\.<3,id:\\\.self\)\{lane in.*?(?=\s*ForEach\(model\.audioClips\)\{a in)',re.S)
lane_background=r'''ForEach(0..<model.trackCount,id:\.self){lane in
                let top=laneTop(lane),laneH=laneHeight(lane)
                Rectangle()
                    .fill(Color.secondary.opacity(0.055))
                    .frame(height:max(32,laneH-1))
                    .offset(y:top)
                if expandedLanes.contains(lane){
                    Rectangle()
                        .fill(Color.accentColor.opacity(0.025))
                        .frame(height:curveH-1)
                        .offset(y:top+laneH)
                    Text("Speed")
                        .font(.system(size:8,weight:.semibold))
                        .foregroundStyle(.secondary)
                        .position(x:18,y:top+laneH+10)
                }
            }
'''
s,n=lane_group_pat.subn(lane_background,s,count=1)
if n!=1:
    raise RuntimeError('universal lane group missing')

s=s.replace('(0..<3).reduce(CGFloat.zero)', '(0..<model.trackCount).reduce(CGFloat.zero)',1)
s=s.replace('let base:CGFloat = 22 + 42 + 12','let base:CGFloat = 22 + 12',1)

scale='Slider(value:$model.trackHeightScale,in:0.65...1.8).frame(width:92)'
if scale not in s:
    raise RuntimeError('track scale slider missing')
s=s.replace(scale,scale+';Button{model.addTrack()}label:{Image(systemName:"rectangle.stack.badge.plus")}.accessibilityLabel("Добавить дорожку")',1)

audio_pos_pat=re.compile(r'\.position\(x:x,y:top\+laneH/2\)\.highPriorityGesture\(')
s,n=audio_pos_pat.subn('.position(x:x,y:top+laneH/2).onTapGesture{model.selectAudioClip(a.id)}.highPriorityGesture(',s,count=1)
if n!=1:
    raise RuntimeError('audio card gesture anchor missing')

playhead_anchor='            Rectangle().fill(Color.accentColor).frame(width:2).position(x:center,y:geo.size.height/2).allowsHitTesting(false);'
if playhead_anchor not in s:
    raise RuntimeError('playhead anchor missing')
fixed_controls=r'''            ForEach(0..<model.trackCount,id:\.self){lane in
                let top=laneTop(lane),laneH=laneHeight(lane),panelW:CGFloat=154
                ZStack{
                    Rectangle()
                        .fill(Color(uiColor:.tertiarySystemGroupedBackground).opacity(0.98))
                        .frame(width:panelW,height:max(32,laneH-1))
                        .overlay(Rectangle().stroke(Color.primary.opacity(0.07),lineWidth:0.5))
                    HStack(spacing:3){
                        Menu{
                            Button("Переименовать"){renamingLane=lane;renameTrackText=trackNames[lane] ?? "V\(lane+1)";showRenameTrack=true}
                            Button("Удалить содержимое",role:.destructive){
                                for c in model.clips.filter({$0.track==lane}){model.deleteClip(c.id)}
                                for a in model.audioClips.filter({$0.track==lane}){model.deleteAudioClip(a.id)}
                            }
                        }label:{
                            Text(trackNames[lane] ?? "V\(lane+1)")
                                .font(.system(size:9,weight:.semibold))
                                .lineLimit(1)
                                .frame(width:39,height:26)
                                .background(Color.primary.opacity(0.06))
                        }
                        .buttonStyle(.plain)

                        Button{model.toggleTrackBypass(lane)}label:{
                            Text("B").font(.system(size:9,weight:.bold))
                                .frame(width:22,height:26)
                                .background(model.bypassedTracks.contains(lane) ? Color.orange.opacity(0.34):Color.primary.opacity(0.055))
                        }.buttonStyle(.plain)

                        Button{model.toggleTrackMute(lane)}label:{
                            Image(systemName:model.mutedTracks.contains(lane) ? "speaker.slash.fill":"speaker.wave.2.fill")
                                .font(.system(size:10,weight:.semibold))
                                .frame(width:24,height:26)
                                .background(model.mutedTracks.contains(lane) ? Color.red.opacity(0.20):Color.primary.opacity(0.055))
                        }.buttonStyle(.plain)

                        Menu{
                            Button{pendingMediaLane=lane;showTrackMediaPicker=true}label:{Label("Видео / Фото",systemImage:"photo.on.rectangle")}
                            Button{pendingExtractLane=lane;showTrackExtractPicker=true}label:{Label("Аудио из видео",systemImage:"video.badge.waveform")}
                            Button{pendingAudioLane=lane;model.isAudioImporting=true}label:{Label("Аудиофайл",systemImage:"waveform.badge.plus")}
                            Button{inspector = .text}label:{Label("Текст",systemImage:"textformat")}
                            Button{inspector = .filters}label:{Label("FX / Фильтр",systemImage:"sparkles")}
                            Button{inspector = .speed}label:{Label("Speed FX",systemImage:"waveform.path.ecg.rectangle")}
                        }label:{
                            Image(systemName:"plus")
                                .font(.system(size:11,weight:.bold))
                                .frame(width:24,height:26)
                                .background(Color.accentColor.opacity(0.16))
                        }.buttonStyle(.plain)

                        Button{
                            if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}
                        }label:{
                            Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down")
                                .font(.system(size:9,weight:.bold))
                                .frame(width:22,height:26)
                                .background(Color.primary.opacity(0.055))
                        }.buttonStyle(.plain)
                    }
                }
                .position(x:77,y:top+laneH/2)
                .zIndex(40)

                LaneHeightHandleV4(height:laneH){newHeight in
                    laneHeights[lane]=newHeight/max(0.65,CGFloat(model.trackHeightScale))
                }
                .position(x:146,y:top+laneH-6)
                .zIndex(41)
            }
'''
s=s.replace(playhead_anchor,fixed_controls+playhead_anchor,1)

s=s.replace('Button{model.splitAtPlayhead()}label:{Image(systemName:"scissors")','Button{if model.selectedAudioClipID != nil{model.splitSelectedAudioAtPlayhead()}else{model.splitAtPlayhead()}}label:{Image(systemName:"scissors")',1)

bottom_pat=re.compile(r'    private var bottomBar:some View\{.*?\n    private func tool\(',re.S)
bottom_repl=r'''    private var bottomBar:some View{
        Group{
            if let audio=model.selectedAudioClip {
                VStack(spacing:6){
                    HStack(spacing:8){
                        Image(systemName:"waveform").font(.system(size:12,weight:.bold))
                        Text(audio.name).font(.caption.weight(.semibold)).lineLimit(1)
                        Spacer()
                        Text(String(format:"%.1fs",audio.duration)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal,10)

                    HStack(spacing:6){
                        audioTool("scissors","Разрезать"){model.splitSelectedAudioAtPlayhead()}
                        audioTool("arrow.right.to.line.compact","Начало"){model.trimSelectedAudioStartToPlayhead()}
                        audioTool("arrow.left.to.line.compact","Конец"){model.trimSelectedAudioEndToPlayhead()}
                        audioTool("plus.square.on.square","Копия"){model.duplicateSelectedAudio()}
                        audioTool("trash","Удалить",role:.destructive){model.deleteSelectedAudio()}
                    }
                    .padding(.horizontal,8)

                    HStack(spacing:8){
                        Image(systemName:"speaker.wave.2").font(.caption)
                        Slider(value:Binding(get:{model.selectedAudioClip?.volume ?? 1},set:{model.setSelectedAudioVolume($0)}),in:0...2)
                        Text(String(format:"%d%%",Int((model.selectedAudioClip?.volume ?? 1)*100))).font(.caption2.monospacedDigit()).frame(width:38)
                    }
                    .padding(.horizontal,10)
                }
                .padding(.vertical,7)
                .background(Color(uiColor:.secondarySystemGroupedBackground))
            }else{
                ScrollView(.horizontal,showsIndicators:false){
                    HStack(spacing:2){
                        tool("scissors","Обрезка",.trim)
                        tool("speedometer","Скорость",.speed)
                        tool("waveform","Аудио",.audio)
                        tool("textformat","Текст",.text)
                        tool("camera.filters","Фильтры",.filters)
                        tool("slider.horizontal.3","Настройка",.adjust)
                        tool("wand.and.stars","Улучшить",.enhance)
                    }.padding(.horizontal,8)
                }
                .padding(.vertical,5)
                .background(Color(uiColor:.secondarySystemGroupedBackground))
                .disabled(model.clips.isEmpty)
            }
        }
    }

    @ViewBuilder private func audioTool(_ icon:String,_ title:String,role:ButtonRole?=nil,_ action:@escaping()->Void)->some View{
        Button(role:role,action:action){
            VStack(spacing:3){
                Image(systemName:icon).font(.system(size:15))
                Text(title).font(.system(size:9)).lineLimit(1)
            }
            .frame(width:55,height:42)
            .background(Color.primary.opacity(0.045))
        }
        .buttonStyle(.plain)
    }

    private func tool('''
s,n=bottom_pat.subn(bottom_repl,s,count=1)
if n!=1:
    raise RuntimeError('bottom bar block missing')

s=s.replace('.frame(width:72,height:50)', '.frame(width:58,height:44).background(Color.primary.opacity(0.035))')
s=s.replace('cornerRadius:22','cornerRadius:8')
s=s.replace('cornerRadius:18','cornerRadius:6')
s=s.replace('cornerRadius:10','cornerRadius:6')

p.write_text(s)
print('Applied v0.5.5 dynamic fixed tracks, mute, audio edit bar, no dedicated FX lane, square UI')
