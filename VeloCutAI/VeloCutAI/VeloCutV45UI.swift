import SwiftUI
import AVFoundation
import UIKit

enum SpeedProcessingMode: String, CaseIterable, Identifiable {
    case fast = "Fast"
    case smooth = "Smooth"
    var id: String { rawValue }
}

struct TimelineFilmstripV45: View {
    let clip: EditorClip
    let width: CGFloat
    let height: CGFloat
    @State private var images: [UIImage] = []

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                if images.isEmpty {
                    Rectangle().fill(Color.secondary.opacity(0.12))
                    Rectangle().fill(Color.secondary.opacity(0.08))
                    Rectangle().fill(Color.secondary.opacity(0.12))
                } else {
                    ForEach(Array(images.enumerated()), id: \.offset) { _, image in
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                            .frame(width: geo.size.width / CGFloat(max(1, images.count)), height: geo.size.height)
                            .clipped()
                    }
                }
            }
            .clipped()
        }
        .task(id: "\(clip.id.uuidString)-\(Int(width))-\(Int(height))") {
            guard images.isEmpty else { return }
            let count = min(10, max(2, Int(width / 44)))
            images = await makeFrames(count: count)
        }
    }

    private func makeFrames(count: Int) async -> [UIImage] {
        let url = clip.url
        let start = clip.trimStart
        let duration = max(0.05, clip.sourceDuration)
        let target = CGSize(width: 180, height: max(80, height * 2))
        return await Task.detached(priority: .utility) {
            let asset = AVURLAsset(url: url)
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = target
            generator.requestedTimeToleranceBefore = CMTime(seconds: 0.08, preferredTimescale: 600)
            generator.requestedTimeToleranceAfter = CMTime(seconds: 0.08, preferredTimescale: 600)
            var result: [UIImage] = []
            for index in 0..<count {
                let fraction = count <= 1 ? 0.5 : Double(index) / Double(count - 1)
                let seconds = start + duration * fraction
                let time = CMTime(seconds: seconds, preferredTimescale: 600)
                if let cg = try? generator.copyCGImage(at: time, actualTime: nil) {
                    result.append(UIImage(cgImage: cg))
                }
            }
            return result
        }.value
    }
}

struct FilmstripClipCardV45: View {
    let clip: EditorClip
    let index: Int
    let width: CGFloat
    let height: CGFloat
    let selected: Bool
    let multiSelected: Bool
    let onTap: () -> Void
    let onMenu: () -> Void
    let onMove: (CGSize) -> Void
    @State private var drag: CGSize = .zero

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 7)
                .fill(Color.secondary.opacity(0.10))

            TimelineFilmstripV45(clip: clip, width: width, height: height)
                .clipShape(RoundedRectangle(cornerRadius: 7))

            LinearGradient(
                colors: [.black.opacity(0.35), .clear, .black.opacity(0.42)],
                startPoint: .top,
                endPoint: .bottom
            )
            .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(spacing: 0) {
                HStack(spacing: 4) {
                    Text("\(index + 1)")
                        .font(.system(size: 8, weight: .bold))
                    Spacer()
                    Text("\(clip.baseSpeed, specifier: "%g")×")
                        .font(.system(size: 8, weight: .semibold))
                    if clip.curveEnabled {
                        Image(systemName: "waveform.path.ecg")
                            .font(.system(size: 7, weight: .bold))
                    }
                }
                Spacer()
                HStack {
                    Text(clip.name)
                        .font(.system(size: 8, weight: .medium))
                        .lineLimit(1)
                    Spacer()
                }
            }
            .foregroundStyle(.white)
            .padding(5)

            if multiSelected {
                VStack {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(.white, Color.accentColor)
                            .padding(5)
                        Spacer()
                    }
                    Spacer()
                }
            }
        }
        .frame(width: width, height: max(38, height))
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(multiSelected ? Color.orange : (selected ? Color.accentColor : .clear), lineWidth: multiSelected ? 2.5 : 2)
        )
        .offset(drag)
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
        .highPriorityGesture(
            LongPressGesture(minimumDuration: 0.32)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    if case .second(true, let gesture) = value, let gesture { drag = gesture.translation }
                }
                .onEnded { value in
                    defer { drag = .zero }
                    if case .second(true, let gesture) = value, let gesture {
                        hypot(gesture.translation.width, gesture.translation.height) < 10 ? onMenu() : onMove(gesture.translation)
                    } else {
                        onMenu()
                    }
                }
        )
    }
}

struct ThinTrimHandleV45: View {
    let currentValue: Double
    let pps: Double
    let sourcePerOutput: Double
    let height: CGFloat
    let onBegin: () -> Void
    let onChange: (Double) -> Void
    let onEnd: () -> Void
    @State private var anchorValue: Double?
    @State private var anchorX: CGFloat?

    var body: some View {
        ZStack {
            Rectangle().fill(Color.clear)
            Capsule()
                .fill(Color.white.opacity(0.96))
                .frame(width: 4, height: max(24, height - 6))
                .shadow(color: .black.opacity(0.25), radius: 1)
        }
        .frame(width: 24, height: max(36, height))
        .contentShape(Rectangle())
        .highPriorityGesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .global)
                .onChanged { value in
                    if anchorValue == nil {
                        anchorValue = currentValue
                        anchorX = value.startLocation.x
                        onBegin()
                    }
                    let dx = value.location.x - (anchorX ?? value.startLocation.x)
                    let deltaOutput = Double(dx) / max(1, pps)
                    let deltaSource = deltaOutput * max(0.02, sourcePerOutput)
                    onChange((anchorValue ?? currentValue) + deltaSource)
                }
                .onEnded { _ in
                    anchorValue = nil
                    anchorX = nil
                    onEnd()
                }
        )
    }
}

struct CurveModeTabsV45: View {
    let mode: CurveInterpolation
    let onChange: (CurveInterpolation) -> Void

    var body: some View {
        HStack(spacing: 3) {
            modeButton(.smooth)
            modeButton(.linear)
            modeButton(.sharp)
        }
        .padding(3)
        .background(Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
    }

    private func modeButton(_ value: CurveInterpolation) -> some View {
        Button {
            onChange(value)
        } label: {
            Text(value.rawValue)
                .font(.system(size: 11, weight: mode == value ? .semibold : .regular))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity)
                .frame(height: 30)
                .background(mode == value ? Color(uiColor: .systemBackground) : .clear, in: RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }
}

struct CurveEditorGraphV45: View {
    @ObservedObject var model: EditorViewModel
    let target: CurveTarget
    @Binding var selectedPointID: UUID?
    @State private var editingPointID: UUID?
    @State private var editingHandle: CurveHandleSide?
    @State private var snappedValue: Double?

    var body: some View {
        GeometryReader { geo in
            let curve = model.curve(for: target)
            let space = "curve-v45-\(target.id)"

            ZStack {
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.secondary.opacity(0.07))

                Canvas { context, size in
                    for speed in curveSnapSpeeds {
                        let y = speedY(speed, height: size.height)
                        var grid = Path()
                        grid.move(to: CGPoint(x: 0, y: y))
                        grid.addLine(to: CGPoint(x: size.width, y: y))
                        let active = snappedValue == speed
                        context.stroke(grid, with: .color(active ? .orange.opacity(0.8) : (speed == 1 ? .secondary.opacity(0.38) : .secondary.opacity(0.13))), lineWidth: active ? 1.5 : (speed == 1 ? 1 : 0.5))
                        if [0.2, 0.5, 1, 2, 5, 10].contains(speed) {
                            let label = context.resolve(Text("\(speed, specifier: "%g")×").font(.system(size: 7, design: .monospaced)).foregroundStyle(.secondary))
                            context.draw(label, at: CGPoint(x: 4, y: y - 2), anchor: .bottomLeading)
                        }
                    }

                    var path = Path()
                    for index in 0...180 {
                        let t = Double(index) / 180
                        let p = CGPoint(x: CGFloat(t) * size.width, y: speedY(curve.value(at: t), height: size.height))
                        if index == 0 { path.move(to: p) } else { path.addLine(to: p) }
                    }
                    context.stroke(path, with: .color(.accentColor), lineWidth: 2.5)
                }
                .allowsHitTesting(false)

                Rectangle()
                    .fill(Color.red.opacity(0.88))
                    .frame(width: 1.5)
                    .position(x: CGFloat(model.normalizedPlayhead(for: target)) * geo.size.width, y: geo.size.height / 2)
                    .allowsHitTesting(false)

                if let id = selectedPointID,
                   let point = curve.points.first(where: { $0.id == id }),
                   point.mode != .linear {
                    handleLayer(point: point, size: geo.size, space: space)
                }

                ForEach(curve.points) { point in
                    ZStack {
                        Circle().fill(Color.clear).frame(width: 36, height: 36)
                        Circle()
                            .fill(point.id == selectedPointID ? Color.white : Color.accentColor)
                            .overlay(Circle().stroke(Color.accentColor, lineWidth: 1.5))
                            .frame(width: point.id == selectedPointID ? 14 : 11, height: point.id == selectedPointID ? 14 : 11)
                    }
                    .position(x: CGFloat(point.t) * geo.size.width, y: speedY(point.speed, height: geo.size.height))
                    .contentShape(Circle())
                    .onTapGesture(count: 2) {
                        selectedPointID = point.id
                        model.setCurvePointMode(target, pointID: point.id, mode: .smooth, resetHandles: true)
                        model.haptic(.selection)
                    }
                    .onTapGesture {
                        selectedPointID = point.id
                    }
                    .highPriorityGesture(
                        DragGesture(minimumDistance: 2, coordinateSpace: .named(space))
                            .onChanged { value in
                                selectedPointID = point.id
                                if editingPointID == nil {
                                    editingPointID = point.id
                                    model.beginCurvePointEdit()
                                }
                                let t = min(max(Double(value.location.x / max(1, geo.size.width)), 0), 1)
                                let raw = ySpeed(value.location.y, height: geo.size.height)
                                let snap = snappedCurveSpeed(raw)
                                if snap.snapped != snappedValue, snap.snapped != nil { model.haptic(.selection) }
                                snappedValue = snap.snapped
                                model.moveCurvePointInteractive(target, pointID: point.id, t: t, speed: snap.speed)
                                model.setCurvePlayheadVisual(target, normalized: t)
                            }
                            .onEnded { value in
                                guard editingPointID != nil else { return }
                                let t = min(max(Double(value.location.x / max(1, geo.size.width)), 0), 1)
                                editingPointID = nil
                                snappedValue = nil
                                model.finishCurvePointEdit(target, normalized: t)
                            }
                    )
                }
            }
            .coordinateSpace(name: space)
        }
    }

    @ViewBuilder
    private func handleLayer(point: SpeedPoint, size: CGSize, space: String) -> some View {
        let center = CGPoint(x: CGFloat(point.t) * size.width, y: speedY(point.speed, height: size.height))
        let incoming = CGPoint(x: CGFloat(point.inT) * size.width, y: speedY(point.inSpeed, height: size.height))
        let outgoing = CGPoint(x: CGFloat(point.outT) * size.width, y: speedY(point.outSpeed, height: size.height))

        Canvas { context, _ in
            var p = Path()
            p.move(to: incoming)
            p.addLine(to: center)
            p.addLine(to: outgoing)
            context.stroke(p, with: .color(.orange.opacity(0.85)), lineWidth: 1)
        }
        .allowsHitTesting(false)

        handle(point: point, side: .incoming, position: incoming, size: size, space: space)
        handle(point: point, side: .outgoing, position: outgoing, size: size, space: space)
    }

    private func handle(point: SpeedPoint, side: CurveHandleSide, position: CGPoint, size: CGSize, space: String) -> some View {
        ZStack {
            Circle().fill(Color.clear).frame(width: 30, height: 30)
            Circle()
                .fill(Color.orange)
                .overlay(Circle().stroke(Color.white.opacity(0.85), lineWidth: 1))
                .frame(width: 8, height: 8)
        }
        .position(position)
        .highPriorityGesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .named(space))
                .onChanged { value in
                    if editingHandle == nil {
                        editingHandle = side
                        model.beginCurvePointEdit()
                    }
                    let t = min(max(Double(value.location.x / max(1, size.width)), 0), 1)
                    let speed = ySpeed(value.location.y, height: size.height)
                    model.moveCurveHandleInteractive(target, pointID: point.id, side: side, t: t, speed: speed)
                }
                .onEnded { _ in
                    editingHandle = nil
                    model.finishCurvePointEdit(target)
                }
        )
    }
}
