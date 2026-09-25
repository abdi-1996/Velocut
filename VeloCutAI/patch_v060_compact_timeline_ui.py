from pathlib import Path
import re

main=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=main.read_text()

# 1. Timeline canvas: horizontal drag scrubs, vertical drag belongs to outer ScrollView.
old_drag='''        .gesture(
            DragGesture(minimumDistance:2)
                .onChanged{v in
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)
                }
                .onEnded{_ in timelineDragStart = nil;model.endScrub()}
        )'''
new_drag='''        .simultaneousGesture(
            DragGesture(minimumDistance:8)
                .onChanged{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    if timelineDragStart==nil { timelineDragStart = model.projectTime;model.beginScrub() }
                    model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)
                }
                .onEnded{v in
                    guard abs(v.translation.width) > abs(v.translation.height) else {
                        if timelineDragStart != nil { timelineDragStart=nil;model.endScrub() }
                        return
                    }
                    timelineDragStart=nil
                    model.endScrub()
                }
        )'''
if old_drag not in s:
    raise RuntimeError('exact final timeline drag block missing')
s=s.replace(old_drag,new_drag,1)

# 2. Remove floating Loop / Play / Undo / Redo controls from Preview only.
floating=re.compile(r'''\n\s*HStack\{\n\s*Spacer\(\)\n\s*HStack\(spacing:6\)\{\n\s*Button\{\n\s*model\.projectLoopEnabled\.toggle\(\).*?\n\s*\.padding\(\.bottom,8\)''',re.S)
s,n=floating.subn('',s,count=1)
if n!=1:
    raise RuntimeError('preview floating transport block missing')

# 3. Compact transport bar directly below Preview.
playback_pat=re.compile(r'    private var playback:some View\{.*?\n\n    private var timeline:',re.S)
playback_repl=r'''    private var playback:some View{
        HStack(spacing:6){
            Button{
                model.projectLoopEnabled.toggle()
                model.playbackMode = .project
                model.haptic(.selection)
            }label:{Image(systemName:model.projectLoopEnabled ? "repeat.circle.fill":"repeat").frame(width:28,height:30)}
            .buttonStyle(.plain)

            Button{model.playPause()}label:{
                Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                    .font(.system(size:15,weight:.semibold))
                    .frame(width:36,height:30)
                    .background(Color.primary.opacity(0.065))
            }.buttonStyle(.plain)

            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:27,height:30)}
                .buttonStyle(.plain).disabled(!model.canUndo)
            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:27,height:30)}
                .buttonStyle(.plain).disabled(!model.canRedo)

            Divider().frame(height:18)
            Image(systemName:"rectangle.compress.vertical").font(.system(size:10)).foregroundStyle(.secondary)
            Slider(value:$model.trackHeightScale,in:0.65...1.8)
                .frame(width:58)
                .controlSize(.mini)

            Button{model.addTrack()}label:{
                Image(systemName:"rectangle.stack.badge.plus")
                    .font(.system(size:13,weight:.semibold))
                    .frame(width:28,height:28)
                    .background(Color.primary.opacity(0.05))
            }.buttonStyle(.plain).accessibilityLabel("Добавить дорожку")

            Spacer(minLength:2)
            Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))")
                .font(.system(size:9,design:.monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal,9)
        .frame(height:40)
        .background(Color(uiColor:.secondarySystemGroupedBackground))
    }

    private var timeline:'''
s,n=playback_pat.subn(playback_repl,s,count=1)
if n!=1:
    raise RuntimeError('final playback block missing')

# 4. Remove entire old timeline header. Keep only vertically scrollable timeline body.
timeline_pat=re.compile(r'    private var timeline:some View\{.*?\n\n    @ViewBuilder private func timelineCanvas',re.S)
timeline_repl=r'''    private var timeline:some View{
        ScrollView(.vertical,showsIndicators:true){
            GeometryReader{geo in timelineCanvas(geo)}
                .frame(height:timelineRequiredHeight)
        }
        .frame(minHeight:180,maxHeight:.infinity)
        .background(Color(uiColor:.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius:6))
        .padding(.horizontal,8)
    }

    @ViewBuilder private func timelineCanvas'''
s,n=timeline_pat.subn(timeline_repl,s,count=1)
if n!=1:
    raise RuntimeError('final timeline wrapper missing')

# 5. Audio selection swaps the SAME bottom toolbar, CapCut-style.
bottom_pat=re.compile(r'    private var bottomBar:some View\{.*?\n    @ViewBuilder private func audioTool\(.*?\n    private func tool\(',re.S)
bottom_repl=r'''    private var bottomBar:some View{
        ScrollView(.horizontal,showsIndicators:false){
            HStack(spacing:3){
                if model.selectedAudioClip != nil {
                    audioTool("scissors","Разрезать"){model.splitSelectedAudioAtPlayhead()}
                    audioTool("arrow.right.to.line.compact","Начало"){model.trimSelectedAudioStartToPlayhead()}
                    audioTool("arrow.left.to.line.compact","Конец"){model.trimSelectedAudioEndToPlayhead()}
                    Menu{
                        Button("0%") { model.setSelectedAudioVolume(0) }
                        Button("25%") { model.setSelectedAudioVolume(0.25) }
                        Button("50%") { model.setSelectedAudioVolume(0.5) }
                        Button("100%") { model.setSelectedAudioVolume(1) }
                        Button("150%") { model.setSelectedAudioVolume(1.5) }
                        Button("200%") { model.setSelectedAudioVolume(2) }
                    }label:{
                        VStack(spacing:3){
                            Image(systemName:"speaker.wave.2").font(.system(size:15))
                            Text("Громкость").font(.system(size:9))
                        }.frame(width:58,height:44).background(Color.primary.opacity(0.04))
                    }.buttonStyle(.plain)
                    audioTool("plus.square.on.square","Копия"){model.duplicateSelectedAudio()}
                    audioTool("trash","Удалить",role:.destructive){model.deleteSelectedAudio()}
                }else{
                    tool("scissors","Обрезка",.trim)
                    tool("speedometer","Скорость",.speed)
                    Button{
                        model.addFlatSpeedFX()
                        if let id=model.speedFX.last?.id { curveTarget = .global(id) }
                    }label:{
                        VStack(spacing:3){
                            Image(systemName:"waveform.path.ecg.rectangle").font(.system(size:15))
                            Text("Speed FX").font(.system(size:9)).lineLimit(1)
                        }.frame(width:58,height:44).background(Color.primary.opacity(0.035))
                    }.buttonStyle(.plain)
                    tool("waveform","Аудио",.audio)
                    tool("textformat","Текст",.text)
                    tool("camera.filters","Фильтры",.filters)
                    tool("slider.horizontal.3","Настройка",.adjust)
                    tool("wand.and.stars","Улучшить",.enhance)
                }
            }.padding(.horizontal,8)
        }
        .frame(height:54)
        .background(Color(uiColor:.secondarySystemGroupedBackground))
    }

    @ViewBuilder private func audioTool(_ icon:String,_ title:String,role:ButtonRole?=nil,_ action:@escaping()->Void)->some View{
        Button(role:role,action:action){
            VStack(spacing:3){
                Image(systemName:icon).font(.system(size:15))
                Text(title).font(.system(size:9)).lineLimit(1)
            }
            .frame(width:58,height:44)
            .background(Color.primary.opacity(0.04))
        }.buttonStyle(.plain)
    }

    private func tool('''
s,n=bottom_pat.subn(bottom_repl,s,count=1)
if n!=1:
    raise RuntimeError('v0.5.5 contextual bottom bar missing')

main.write_text(s)

# 6. Make the visible per-track resize line smaller, but KEEP a generous touch target.
enh=Path('VeloCutAI/VeloCutAI/VeloCutV4Enhancements.swift')
e=enh.read_text()
old='Capsule().fill(Color.secondary.opacity(0.6)).frame(width: 32, height: 5)'
new='Capsule().fill(Color.secondary.opacity(0.55)).frame(width: 18, height: 3)'
if old not in e:
    raise RuntimeError('LaneHeightHandleV4 visible capsule missing')
e=e.replace(old,new,1)
enh.write_text(e)

print('Applied v0.5.6 final compact controls, vertical scrolling and CapCut-style audio toolbar')
