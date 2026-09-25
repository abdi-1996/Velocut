from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

pattern = re.compile(r'struct CurveEditorPanel:View \{.*?\n\}\n\nstruct InspectorSheet:View', re.S)
replacement = r'''struct CurveEditorPanel:View {
    @ObservedObject var model:EditorViewModel
    let target:CurveTarget
    let onClose:()->Void
    @State private var selectedPoint:UUID?

    var body:some View {
        VStack(spacing:10) {
            HStack {
                Button(action:onClose) { Image(systemName:"chevron.down.circle.fill").font(.title2) }
                VStack(alignment:.leading) {
                    Text(title).font(.headline)
                    Text("Коснитесь точки и сразу тяните • двойной тап по точке = Smooth")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    ForEach(SpeedCurvePreset.all) { preset in
                        Button("\(preset.category) • \(preset.name)") { model.applyPreset(preset,to:target) }
                    }
                } label: {
                    Label("Шаблоны",systemImage:"sparkles").font(.caption)
                }
            }
            .padding(.horizontal,14)

            ScrollView(.horizontal,showsIndicators:false) {
                HStack(spacing:8) {
                    ForEach(SpeedCurvePreset.all) { preset in
                        Button { model.applyPreset(preset,to:target) } label: {
                            VStack(spacing:3) {
                                CurveThumbnail(curve:preset.curve,lineWidth:1.5).frame(width:78,height:30)
                                Text(preset.name).font(.system(size:8)).lineLimit(1)
                                Text(preset.category).font(.system(size:7)).foregroundStyle(.secondary)
                            }
                            .frame(width:86)
                            .padding(6)
                            .background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal,12)
            }

            HStack(spacing:10) {
                Button { model.playCurveFromStart(target) } label: {
                    Label("С начала",systemImage:"backward.end.fill")
                }
                .buttonStyle(.bordered)

                Button { model.toggleCurvePlayback() } label: {
                    Image(systemName:model.isPlaying ? "pause.fill":"play.fill")
                        .frame(width:28,height:20)
                }
                .buttonStyle(.borderedProminent)

                Spacer()
                Text(String(format:"%.2fс",model.curveProjectTime(target,normalized:model.normalizedPlayhead(for:target))))
                    .font(.caption.monospacedDigit().weight(.semibold))
            }
            .padding(.horizontal,14)

            VStack(spacing:4) {
                Slider(
                    value:Binding(
                        get:{model.normalizedPlayhead(for:target)},
                        set:{model.seekCurveTarget(target,normalized:$0)}
                    ),
                    in:0...1
                )
                HStack {
                    Text(timeText(0))
                    Spacer()
                    Text("Preview ↔ Playhead ↔ Curve").font(.caption2.weight(.semibold))
                    Spacer()
                    Text(timeText(1))
                }
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal,14)

            CurveEditorGraphV4(model:model,target:target,selectedPointID:$selectedPoint)
                .frame(minHeight:205)
                .padding(.horizontal,12)

            if let pointID=selectedPoint, let point=model.curve(for:target).points.first(where:{$0.id==pointID}) {
                HStack(spacing:10) {
                    Text(String(format:"Точка %.2f×",point.speed))
                        .font(.caption.monospacedDigit().weight(.semibold))

                    Picker("Тип",selection:Binding(
                        get:{point.mode},
                        set:{newMode in model.setCurvePointMode(target,pointID:pointID,mode:newMode,resetHandles:newMode == .smooth)}
                    )) {
                        ForEach(CurveInterpolation.allCases) { mode in Text(mode.rawValue).tag(mode) }
                    }
                    .pickerStyle(.segmented)

                    if point.mode != .linear {
                        Button { model.resetCurvePointHandles(target,pointID:pointID) } label: {
                            Image(systemName:"arrow.counterclockwise")
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal,14)

                Text(point.mode == .linear ? "Linear: прямая линия без направляющих" : (point.mode == .smooth ? "Smooth: две связанные направляющие" : "Sharp: направляющие двигаются независимо"))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal,14)
                    .frame(maxWidth:.infinity,alignment:.leading)
            }

            HStack {
                Button { model.addCurvePoint(target,t:model.normalizedPlayhead(for:target)) } label: {
                    Label("Точка",systemImage:"plus.circle")
                }
                Button { model.mirrorCurve(target) } label: {
                    Label("Mirror",systemImage:"arrow.left.and.right")
                }
                if let id=selectedPoint {
                    Button(role:.destructive) { model.deleteCurvePoint(target,pointID:id);selectedPoint=nil } label: {
                        Image(systemName:"trash")
                    }
                }
                Spacer()
                Text("Snap: 0.1 • 0.2 • 0.25 • 0.5 • 1 • 2 • 5 • 10 • 20×")
                    .font(.system(size:8))
                    .foregroundStyle(.secondary)
            }
            .font(.caption)
            .padding(.horizontal,14)

            if case .global(let id)=target,let fx=model.speedFX.first(where:{$0.id==id}) {
                VStack(spacing:8) {
                    HStack {
                        Text("Strength")
                        Slider(value:Binding(get:{fx.strength},set:{model.setSpeedFXStrength(id,$0)}),in:0...2)
                        Text("\(fx.strength,specifier:"%.1f")×").monospacedDigit()
                    }
                    HStack {
                        Text("Длина")
                        Slider(value:Binding(get:{fx.duration},set:{model.setSpeedFXDuration(id,$0)}),in:0.15...4)
                        Text("\(fx.duration,specifier:"%.2f")с").monospacedDigit()
                    }
                    HStack {
                        Picker("Режим",selection:Binding(get:{fx.mode},set:{model.setSpeedFXMode(id,$0)})) {
                            ForEach(SpeedFXMode.allCases) { Text($0.rawValue).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        Button { model.duplicateSpeedFX(id) } label: { Image(systemName:"plus.square.on.square") }
                        Button { model.repeatSpeedFX(id,count:4) } label: { Text("×4") }
                    }
                }
                .font(.caption)
                .padding(.horizontal,14)
            }
            Spacer(minLength:4)
        }
        .padding(.vertical,8)
        .background(.regularMaterial)
    }

    private var title:String {
        switch target {
        case .clip:return "Speed Curve клипа"
        case .global:return "Global Speed FX"
        }
    }

    private func timeText(_ normalized:Double)->String {
        String(format:"%.2fс",model.curveProjectTime(target,normalized:normalized))
    }
}

struct InspectorSheet:View'''

s, count = pattern.subn(replacement, s, count=1)
if count != 1:
    raise RuntimeError('Patched CurveEditorPanel not found for v0.4.4')

p.write_text(s)
print('Applied v0.4.4 per-point curve UI and playback controls')
