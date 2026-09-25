from pathlib import Path
import re
p=Path('VeloCutAI/patch_v053_universal_tracks.py')
s=p.read_text()
start=s.index('# Replace only the lane header row inside original timelineCanvas.')
end=s.index('# Media loader for lane +.')
replacement=r"""# Replace only the original three-lane drawing section. Everything before/after it stays v0.5.
new_lane='''ForEach(0..<3,id:\\.self){lane in
                let top=laneTop(lane)
                let laneH:CGFloat=46
                RoundedRectangle(cornerRadius:8).fill(Color.secondary.opacity(0.06)).frame(height:laneH-3).offset(y:top)
                Menu{
                    Button(\"Переименовать\"){trackNames[lane]=\"Track \\(lane+1)\"}
                    Button(\"Удалить содержимое\",role:.destructive){for c in model.clips.filter({$0.track==lane}){model.deleteClip(c.id)};for a in model.audioClips.filter({$0.track==lane}){model.deleteAudioClip(a.id)}}
                }label:{Text(trackNames[lane] ?? \"V\\(lane+1)\").font(.system(size:9,weight:.bold)).lineLimit(1).frame(width:38,height:28).background(Color.accentColor.opacity(0.22),in:RoundedRectangle(cornerRadius:7))}.buttonStyle(.plain).position(x:24,y:top+laneH/2)
                Button{model.toggleTrackBypass(lane)}label:{Text(\"B\").font(.system(size:9,weight:.bold)).frame(width:23,height:25).background(model.bypassedTracks.contains(lane) ? Color.orange.opacity(0.42):Color.secondary.opacity(0.13),in:RoundedRectangle(cornerRadius:6))}.buttonStyle(.plain).position(x:58,y:top+laneH/2)
                Menu{
                    Button{pendingMediaLane=lane;showTrackMediaPicker=true}label:{Label(\"Видео / Фото\",systemImage:\"photo.on.rectangle\")}
                    Button{pendingAudioLane=lane;model.isAudioImporting=true}label:{Label(\"Аудиофайл\",systemImage:\"waveform.badge.plus\")}
                    Button{pendingExtractLane=lane;showTrackExtractPicker=true}label:{Label(\"Извлечь аудио из видео\",systemImage:\"video.badge.waveform\")}
                    Button{inspector = .text}label:{Label(\"Текст\",systemImage:\"textformat\")}
                    Button{inspector = .filters}label:{Label(\"FX / Фильтр\",systemImage:\"sparkles\")}
                    Button{inspector = .speed}label:{Label(\"Speed FX\",systemImage:\"waveform.path.ecg.rectangle\")}
                }label:{Image(systemName:\"plus.circle.fill\").font(.system(size:18)).frame(width:30,height:30)}.buttonStyle(.plain).position(x:geo.size.width-18,y:top+laneH/2)
                Button{if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}}label:{Image(systemName:expandedLanes.contains(lane) ? \"chevron.up\":\"chevron.down\").font(.system(size:8,weight:.bold)).frame(width:20,height:20).background(.thinMaterial,in:Circle())}.buttonStyle(.plain).position(x:84,y:top+laneH/2)
                if expandedLanes.contains(lane){RoundedRectangle(cornerRadius:7).fill(Color.accentColor.opacity(0.035)).frame(height:curveH-2).offset(y:top+laneH);Text(\"Speed\").font(.system(size:8,weight:.semibold)).foregroundStyle(.secondary).position(x:22,y:top+laneH+10)}
            }
            ForEach(model.audioClips){a in
                let laneH:CGFloat=46
                let w=max(54,a.duration*pps),x=center+(a.start-model.projectTime)*pps+w/2,top=laneTop(a.track)
                HStack(spacing:4){Image(systemName:\"waveform\").font(.system(size:9));Text(a.name).font(.system(size:8,weight:.semibold)).lineLimit(1)}.padding(.horizontal,7).frame(width:w,height:38).background(Color.cyan.opacity(model.bypassedTracks.contains(a.track) ? 0.08:0.22),in:RoundedRectangle(cornerRadius:8)).overlay(RoundedRectangle(cornerRadius:8).stroke(Color.cyan.opacity(0.55),lineWidth:1)).position(x:x,y:top+laneH/2).highPriorityGesture(LongPressGesture(minimumDuration:0.28).sequenced(before:DragGesture(minimumDistance:0)).onEnded{v in if case .second(true,let d?)=v{if hypot(d.translation.width,d.translation.height)<8{model.deleteAudioClip(a.id)}else{model.moveAudioClip(a.id,translation:d.translation,pps:pps)}}})
            }
            ForEach(Array(model.layouts.enumerated()),id:\\.element.id){index,l in'''
lane_pat=re.compile(r'ForEach\(0\.\.<3\s*,\s*id:\s*\\\.self\)\s*\{\s*lane in.*?ForEach\(Array\(model\.layouts\.enumerated\(\)\)\s*,\s*id:\s*\\\.element\.id\)\s*\{\s*index\s*,\s*l in',re.S)
s,n=lane_pat.subn(new_lane,s,count=1)
if n!=1: raise RuntimeError('v0.5 lane section missing')

"""
s=s[:start]+replacement+s[end:]
p.write_text(s)
print('Relaxed v0.5 universal lane matcher without touching timeline navigation')
