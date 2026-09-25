from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# VeloCut v0.5.6: compact controls + true vertical track scrolling.

# Make the existing timeline scrub coexist with the outer vertical ScrollView.
if '.gesture(DragGesture(minimumDistance:12)' not in s:
    raise RuntimeError('timeline gesture prefix missing')
s=s.replace('.gesture(DragGesture(minimumDistance:12)', '.simultaneousGesture(DragGesture(minimumDistance:12)',1)

changed='onChanged{v in if timelineDragStart==nil{'
if changed not in s:
    raise RuntimeError('timeline onChanged prefix missing')
s=s.replace(changed,'onChanged{v in guard abs(v.translation.width)>abs(v.translation.height) else{return};if timelineDragStart==nil{',1)

ended='onEnded{v in let base=timelineDragStart ?? model.projectTime;'
if ended not in s:
    raise RuntimeError('timeline onEnded prefix missing')
s=s.replace(ended,'onEnded{v in guard let base=timelineDragStart else{return};',1)

# Remove floating Loop/Play/Undo/Redo from Preview.
floating=re.compile(r'''\n\s*HStack\{\n\s*Spacer\(\)\n\s*HStack\(spacing:6\)\{\n\s*Button\{\n\s*model\.projectLoopEnabled\.toggle\(\).*?\.padding\(\.bottom,8\)''',re.S)
s,n=floating.subn('',s,count=1)
if n!=1:
    raise RuntimeError('floating preview controls missing')

# Compact under-preview transport + small track-height scale + add-track.
playback_pat=re.compile(r'    private var playback:some View\{.*?\n\n    private var timeline:',re.S)
playback_repl=r'''    private var playback:some View{
        HStack(spacing:7){
            Button{
                model.projectLoopEnabled.toggle()
                model.playbackMode = .project
                model.haptic(.selection)
            }label:{Image(systemName:model.projectLoopEnabled ? "repeat.circle.fill":"repeat").frame(width:30,height:30)}
            .buttonStyle(.plain)

            Button{model.playPause()}label:{
                Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                    .font(.system(size:16,weight:.semibold))
                    .frame(width:36,height:32)
                    .background(Color.primary.opacity(0.07))
            }.buttonStyle(.plain)

            Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward").frame(width:28,height:30)}
                .buttonStyle(.plain).disabled(!model.canUndo)
            Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward").frame(width:28,height:30)}
                .buttonStyle(.plain).disabled(!model.canRedo)

            Divider().frame(height:20)
            Image(systemName:"rectangle.compress.vertical").font(.system(size:11)).foregroundStyle(.secondary)
            Slider(value:$model.trackHeightScale,in:0.65...1.8).frame(width:62).controlSize(.mini)

            Button{model.addTrack()}label:{
                Image(systemName:"rectangle.stack.badge.plus")
                    .font(.system(size:14,weight:.semibold))
                    .frame(width:30,height:30)
                    .background(Color.primary.opacity(0.055))
            }.buttonStyle(.plain).accessibilityLabel("Добавить дорожку")

            Spacer(minLength:4)
            Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))")
                .font(.caption2.monospacedDigit()).foregroundStyle(.secondary).lineLimit(1)
        }
        .padding(.horizontal,10)
        .frame(height:42)
        .background(Color(uiColor:.secondarySystemGroupedBackground))
    }

    private var timeline:'''
s,n=playback_pat.subn(playback_repl,s,count=1)
if n!=1:
    raise RuntimeError('playback/timeline boundary missing')

# Remove the old Timeline / slider / Speed FX / zoom header entirely.
timeline_pat=re.compile(r'    private var timeline:some View\{.*?\n\n    @ViewBuilder private func timelineCanvas',re.S)
timeline_repl=r'''    private var timeline:some View{
        ScrollView(.vertical,showsIndicators:true){
            GeometryReader{geo in timelineCanvas(geo)}
                .frame(height:timelineRequiredHeight)
        }
        .frame(minHeight:230,maxHeight:.infinity)
        .background(Color(uiColor:.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius:6))
        .padding(.horizontal,8)
    }

    @ViewBuilder private func timelineCanvas'''
s,n=timeline_pat.subn(timeline_repl,s,count=1)
if n!=1:
    raise RuntimeError('timeline view block missing')

# Audio selection swaps the existing bottom toolbar; no tall audio panel.
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
                        VStack(spacing:3){Image(systemName:"speaker.wave.2").font(.system(size:15));Text("Громкость").font(.system(size:9))}
                            .frame(width:58,height:44).background(Color.primary.opacity(0.045))
                    }.buttonStyle(.plain)
                    audioTool("plus.square.on.square","Копия"){model.duplicateSelectedAudio()}
                    audioTool("trash","Удалить",role:.destructive){model.deleteSelectedAudio()}
                }else{
                    tool("scissors","Обрезка",.trim)
                    tool("speedometer","Скорость",.speed)
                    Button{
                        model.addFlatSpeedFX()
                        if let id=model.speedFX.last?.id{curveTarget = .global(id)}
                    }label:{
                        VStack(spacing:3){Image(systemName:"waveform.path.ecg.rectangle").font(.system(size:15));Text("Speed FX").font(.system(size:9)).lineLimit(1)}
                            .frame(width:58,height:44).background(Color.primary.opacity(0.035))
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
            VStack(spacing:3){Image(systemName:icon).font(.system(size:15));Text(title).font(.system(size:9)).lineLimit(1)}
                .frame(width:58,height:44).background(Color.primary.opacity(0.045))
        }.buttonStyle(.plain)
    }

    private func tool('''
s,n=bottom_pat.subn(bottom_repl,s,count=1)
if n!=1:
    raise RuntimeError('v0.5.5 bottom audio toolbar missing')

p.write_text(s)
print('Applied v0.5.6 compact preview controls, vertical timeline scroll and contextual bottom toolbar')
