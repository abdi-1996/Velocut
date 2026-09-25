import SwiftUI
import AVKit
import Foundation
import UIKit

// Extra editing interactions layered on top of the original v0.4 editor.
extension EditorViewModel {
    func beginInteractiveEdit() {
        player.pause()
        isPlaying = false
        registerUndo()
    }

    func finishInteractiveEdit() {
        projectTime = min(max(0, projectTime), projectDuration)
        schedulePreview(immediate: true)
    }

    func setTrimStartInteractive(_ id: UUID, _ value: Double) {
        guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
        objectWillChange.send()
        clips[i].trimStart = min(max(0, value), clips[i].trimEnd - 0.05)
        selectedClipID = id
    }

    func setTrimEndInteractive(_ id: UUID, _ value: Double) {
        guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
        objectWillChange.send()
        clips[i].trimEnd = max(min(clips[i].duration, value), clips[i].trimStart + 0.05)
        selectedClipID = id
    }

    func setSpeedFXStartInteractive(_ id: UUID, start: Double, duration: Double) {
        guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
        objectWillChange.send()
        speedFX[i].start = max(0, start)
        speedFX[i].duration = max(0.08, duration)
    }

    func setSpeedFXDurationInteractive(_ id: UUID, _ duration: Double) {
        guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
        objectWillChange.send()
        speedFX[i].duration = min(max(duration, 0.08), 8)
    }

    func seekCurveTarget(_ target: CurveTarget, normalized: Double) {
        let n = min(max(normalized, 0), 1)
        switch target {
        case .clip(let id):
            guard let layout = layout(for: id) else { return }
            seekProject(to: layout.start + layout.duration * n, exact: true)
        case .global(let id):
            guard let fx = speedFX.first(where: { $0.id == id }) else { return }
            seekProject(to: fx.start + fx.duration * n, exact: true)
        }
    }

    func setCurvePlayheadVisual(_ target: CurveTarget, normalized: Double) {
        let n = min(max(normalized, 0), 1)
        switch target {
        case .clip(let id):
            guard let layout = layout(for: id) else { return }
            projectTime = min(max(0, layout.start + layout.duration * n), projectDuration)
        case .global(let id):
            guard let fx = speedFX.first(where: { $0.id == id }) else { return }
            projectTime = min(max(0, fx.start + fx.duration * n), projectDuration)
        }
    }

    func curveProjectTime(_ target: CurveTarget, normalized: Double) -> Double {
        let n = min(max(normalized, 0), 1)
        switch target {
        case .clip(let id):
            guard let layout = layout(for: id) else { return projectTime }
            return layout.start + layout.duration * n
        case .global(let id):
            guard let fx = speedFX.first(where: { $0.id == id }) else { return projectTime }
            return fx.start + fx.duration * n
        }
    }

    func beginCurvePointEdit() {
        player.pause()
        isPlaying = false
        registerUndo()
    }

    func moveCurvePointInteractive(_ target: CurveTarget, pointID: UUID, t: Double, speed: Double) {
        objectWillChange.send()
        switch target {
        case .clip(let id):
            guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
            clips[i].speedCurve.movePoint(id: pointID, t: t, speed: speed)
            clips[i].curveEnabled = true
        case .global(let id):
            guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
            speedFX[i].curve.movePoint(id: pointID, t: t, speed: speed)
        }
    }

    func moveCurveHandleInteractive(_ target: CurveTarget, pointID: UUID, side: CurveHandleSide, t: Double, speed: Double) {
        objectWillChange.send()
        switch target {
        case .clip(let id):
            guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
            clips[i].speedCurve.moveHandle(pointID: pointID, side: side, t: t, speed: speed)
            clips[i].curveEnabled = true
        case .global(let id):
            guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
            speedFX[i].curve.moveHandle(pointID: pointID, side: side, t: t, speed: speed)
        }
    }

    func finishCurvePointEdit(_ target: CurveTarget, normalized: Double? = nil) {
        if let normalized { setCurvePlayheadVisual(target, normalized: min(max(normalized, 0), 1)) }
        schedulePreview(immediate: true)
    }

    func setCurvePointMode(_ target: CurveTarget, pointID: UUID, mode: CurveInterpolation, resetHandles: Bool = false) {
        registerUndo()
        objectWillChange.send()
        switch target {
        case .clip(let id):
            guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
            clips[i].speedCurve.setPointMode(pointID, mode: mode, resetHandles: resetHandles)
            clips[i].curveEnabled = true
        case .global(let id):
            guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
            speedFX[i].curve.setPointMode(pointID, mode: mode, resetHandles: resetHandles)
        }
        schedulePreview()
    }

    func resetCurvePointHandles(_ target: CurveTarget, pointID: UUID) {
        registerUndo()
        objectWillChange.send()
        switch target {
        case .clip(let id):
            guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
            clips[i].speedCurve.resetHandles(pointID: pointID)
            clips[i].curveEnabled = true
        case .global(let id):
            guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }
            speedFX[i].curve.resetHandles(pointID: pointID)
        }
        schedulePreview()
    }

    // Playback here intentionally does not rebuild the composition. The base
    // v0.4 periodic AVPlayer observer already updates projectTime at ~30 fps,
    // so the Preview, curve playhead and timeline slider stay synchronized.
    func playCurveFromStart(_ target: CurveTarget) {
        player.pause()
        isPlaying = false
        seekCurveTarget(target, normalized: 0)
        DispatchQueue.main.async { [weak self] in
            self?.player.play()
            self?.isPlaying = true
        }
    }

    func toggleCurvePlayback() {
        if player.rate != 0 {
            player.pause()
            isPlaying = false
        } else {
            player.play()
            isPlaying = true
        }
    }
}

struct FullscreenPreviewV4: View {
    let player: AVPlayer
    let onClose: () -> Void

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            PlayerView(player: player).ignoresSafeArea()
            VStack {
                HStack {
                    Spacer()
                    Button(action: onClose) {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 42, height: 42)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                }
                Spacer()
                Button {
                    if player.rate == 0 { player.play() } else { player.pause() }
                } label: {
                    Image(systemName: player.rate == 0 ? "play.fill" : "pause.fill")
                        .font(.title2)
                        .foregroundStyle(.white)
                        .frame(width: 58, height: 58)
                        .background(.ultraThinMaterial, in: Circle())
                }
            }
            .padding(18)
        }
        .statusBarHidden(true)
    }
}

struct LaneHeightHandleV4: View {
    let height: CGFloat
    let onChange: (CGFloat) -> Void
    @State private var anchorHeight: CGFloat?
    @State private var anchorY: CGFloat?

    var body: some View {
        ZStack {
            Rectangle().fill(Color.clear)
            Capsule().fill(Color.secondary.opacity(0.6)).frame(width: 32, height: 5)
        }
        .frame(width: 50, height: 30)
        .contentShape(Rectangle())
        .highPriorityGesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .global)
                .onChanged { value in
                    if anchorHeight == nil {
                        anchorHeight = height
                        anchorY = value.startLocation.y
                    }
                    let delta = value.location.y - (anchorY ?? value.startLocation.y)
                    onChange(min(max((anchorHeight ?? height) + delta, 38), 150))
                }
                .onEnded { _ in anchorHeight = nil; anchorY = nil }
        )
    }
}

struct TimelineTrimHandleV4: View {
    let leading: Bool
    let currentValue: Double
    let pps: Double
    let sourcePerOutput: Double
    var height: CGFloat = 38
    let onBegin: () -> Void
    let onChange: (Double) -> Void
    var onEnd: () -> Void = {}
    @State private var anchorValue: Double?
    @State private var anchorX: CGFloat?

    var body: some View {
        ZStack {
            Rectangle().fill(Color.clear)
            Capsule()
                .fill(Color.white.opacity(0.96))
                .overlay(Capsule().stroke(Color.accentColor.opacity(0.7), lineWidth: 1))
                .frame(width: 12, height: max(28, height))
        }
        .frame(width: 34, height: max(40, height + 8))
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

struct SpeedFXEdgeHandleV4: View {
    let leading: Bool
    let start: Double
    let duration: Double
    let pps: Double
    let onBegin: () -> Void
    let onChange: (Double, Double) -> Void
    var onEnd: () -> Void = {}
    @State private var anchorStart: Double?
    @State private var anchorDuration: Double?
    @State private var anchorX: CGFloat?

    var body: some View {
        ZStack {
            Rectangle().fill(Color.clear)
            Capsule().fill(Color.white.opacity(0.92)).frame(width: 9, height: 26)
        }
        .frame(width: 32, height: 38)
        .contentShape(Rectangle())
        .highPriorityGesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .global)
                .onChanged { value in
                    if anchorStart == nil {
                        anchorStart = start
                        anchorDuration = duration
                        anchorX = value.startLocation.x
                        onBegin()
                    }
                    let baseStart = anchorStart ?? start
                    let baseDuration = anchorDuration ?? duration
                    let dx = value.location.x - (anchorX ?? value.startLocation.x)
                    let delta = Double(dx) / max(1, pps)
                    if leading {
                        let safeDelta = min(delta, baseDuration - 0.08)
                        let newStart = max(0, baseStart + safeDelta)
                        let actualDelta = newStart - baseStart
                        onChange(newStart, max(0.08, baseDuration - actualDelta))
                    } else {
                        onChange(baseStart, min(max(baseDuration + delta, 0.08), 8))
                    }
                }
                .onEnded { _ in
                    anchorStart = nil
                    anchorDuration = nil
                    anchorX = nil
                    onEnd()
                }
        )
    }
}

struct ResizableTimelineClipCardV4: View {
    let clip: EditorClip
    let index: Int
    let width: Double
    let height: CGFloat
    let selected: Bool
    let onTap: () -> Void
    let onMenu: () -> Void
    let onMove: (CGSize) -> Void
    @State private var drag: CGSize = .zero

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(selected ? Color.accentColor.opacity(0.24) : Color.secondary.opacity(0.14))
            VStack {
                HStack {
                    Text("\(index + 1)").font(.system(size: 8, weight: .bold))
                    Spacer()
                    Text("\(clip.baseSpeed, specifier: "%g")×\(clip.curveEnabled ? " • curve" : "")").font(.system(size: 8))
                }
                Spacer()
                Text(clip.name).font(.system(size: 8)).lineLimit(1)
            }
            .padding(5)
        }
        .frame(width: width, height: max(40, height))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? Color.accentColor : .clear, lineWidth: 2))
        .offset(drag)
        .onTapGesture { onTap() }
        .highPriorityGesture(
            LongPressGesture(minimumDuration: 0.32)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    if case .second(true, let d) = value, let d { drag = d.translation }
                }
                .onEnded { value in
                    defer { drag = .zero }
                    if case .second(true, let d) = value, let d {
                        hypot(d.translation.width, d.translation.height) < 10 ? onMenu() : onMove(d.translation)
                    } else { onMenu() }
                }
        )
    }
}

private struct CurvePointNodeV44: View {
    let point: SpeedPoint
    let selected: Bool
    let size: CGSize
    let coordinateSpaceName: String
    let onSelect: () -> Void
    let onBegin: () -> Void
    let onMove: (Double, Double, Double?) -> Void
    let onEnd: (Double) -> Void
    let onDoubleTap: () -> Void
    @State private var editing = false
    @State private var lastSnap: Double?

    var body: some View {
        ZStack {
            Circle().fill(Color.clear).frame(width: 48, height: 48)
            Circle()
                .fill(selected ? Color.white : Color.accentColor)
                .overlay(Circle().stroke(Color.accentColor, lineWidth: 2))
                .frame(width: selected ? 22 : 17, height: selected ? 22 : 17)
        }
        .contentShape(Circle())
        .position(x: CGFloat(point.t) * size.width, y: speedY(point.speed, height: size.height))
        .onTapGesture(count: 2) {
            onSelect()
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            onDoubleTap()
        }
        .onTapGesture { onSelect() }
        .highPriorityGesture(
            DragGesture(minimumDistance: 2, coordinateSpace: .named(coordinateSpaceName))
                .onChanged { value in
                    onSelect()
                    if !editing { editing = true; onBegin() }
                    let t = min(max(Double(value.location.x / max(1, size.width)), 0), 1)
                    let snap = snappedCurveSpeed(ySpeed(value.location.y, height: size.height))
                    if snap.snapped != lastSnap {
                        if snap.snapped != nil { UISelectionFeedbackGenerator().selectionChanged() }
                        lastSnap = snap.snapped
                    }
                    onMove(t, snap.speed, snap.snapped)
                }
                .onEnded { value in
                    guard editing else { return }
                    let t = min(max(Double(value.location.x / max(1, size.width)), 0), 1)
                    editing = false
                    lastSnap = nil
                    onEnd(t)
                }
        )
    }
}

private struct CurveHandleNodeV44: View {
    let t: Double
    let speed: Double
    let size: CGSize
    let coordinateSpaceName: String
    let onBegin: () -> Void
    let onMove: (Double, Double) -> Void
    let onEnd: () -> Void
    @State private var editing = false

    var body: some View {
        ZStack {
            Circle().fill(Color.clear).frame(width: 36, height: 36)
            Circle().fill(Color.orange).frame(width: 10, height: 10)
                .overlay(Circle().stroke(Color.white.opacity(0.9), lineWidth: 1))
        }
        .position(x: CGFloat(t) * size.width, y: speedY(speed, height: size.height))
        .highPriorityGesture(
            DragGesture(minimumDistance: 1, coordinateSpace: .named(coordinateSpaceName))
                .onChanged { value in
                    if !editing { editing = true; onBegin() }
                    let nt = min(max(Double(value.location.x / max(1, size.width)), 0), 1)
                    let ns = snappedCurveSpeed(ySpeed(value.location.y, height: size.height)).speed
                    onMove(nt, ns)
                }
                .onEnded { _ in
                    if editing { editing = false; onEnd() }
                }
        )
    }
}

struct InlineCurveEditorV4: View {
    @ObservedObject var model: EditorViewModel
    let target: CurveTarget
    let onOpen: () -> Void
    @State private var selectedPointID: UUID?

    var body: some View {
        GeometryReader { geo in
            let curve = model.curve(for: target)
            let spaceName = "inline-v44-\(target.id)"
            ZStack {
                RoundedRectangle(cornerRadius: 7).fill(Color.accentColor.opacity(0.055))
                Canvas { context, size in
                    for speed in [0.2, 0.5, 1, 2, 5, 10] as [Double] {
                        let y = speedY(speed, height: size.height)
                        var grid = Path(); grid.move(to: CGPoint(x: 0, y: y)); grid.addLine(to: CGPoint(x: size.width, y: y))
                        context.stroke(grid, with: .color(.secondary.opacity(speed == 1 ? 0.22 : 0.08)), lineWidth: 0.6)
                    }
                    var path = Path()
                    for i in 0...90 {
                        let t = Double(i) / 90
                        let p = CGPoint(x: CGFloat(t) * size.width, y: speedY(curve.value(at: t), height: size.height))
                        if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
                    }
                    context.stroke(path, with: .color(.accentColor), lineWidth: 2)
                }
                .allowsHitTesting(false)

                Rectangle()
                    .fill(Color.red.opacity(0.9))
                    .frame(width: 1.5)
                    .position(x: CGFloat(model.normalizedPlayhead(for: target)) * geo.size.width, y: geo.size.height / 2)
                    .allowsHitTesting(false)

                ForEach(curve.points) { point in
                    CurvePointNodeV44(
                        point: point,
                        selected: point.id == selectedPointID,
                        size: geo.size,
                        coordinateSpaceName: spaceName,
                        onSelect: { selectedPointID = point.id },
                        onBegin: { model.beginCurvePointEdit() },
                        onMove: { t, speed, _ in
                            model.moveCurvePointInteractive(target, pointID: point.id, t: t, speed: speed)
                            model.setCurvePlayheadVisual(target, normalized: t)
                        },
                        onEnd: { t in model.finishCurvePointEdit(target, normalized: t) },
                        onDoubleTap: { model.setCurvePointMode(target, pointID: point.id, mode: .smooth, resetHandles: true) }
                    )
                }

                VStack {
                    HStack {
                        Spacer()
                        Button(action: onOpen) {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.system(size: 9, weight: .bold))
                                .frame(width: 24, height: 24)
                                .background(.thinMaterial, in: Circle())
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }
                .padding(3)
            }
            .coordinateSpace(name: spaceName)
            .contentShape(Rectangle())
            .onTapGesture(count: 2, coordinateSpace: .named(spaceName)) { location in
                let t = min(max(Double(location.x / max(1, geo.size.width)), 0.01), 0.99)
                model.addCurvePoint(target, t: t, speed: curve.value(at: t))
                model.seekCurveTarget(target, normalized: t)
            }
        }
    }
}

struct CurveEditorGraphV4: View {
    @ObservedObject var model: EditorViewModel
    let target: CurveTarget
    @Binding var selectedPointID: UUID?

    var body: some View {
        GeometryReader { geo in
            let curve = model.curve(for: target)
            let sorted = curve.points.sorted { $0.t < $1.t }
            let spaceName = "curve-v44-\(target.id)"

            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.secondary.opacity(0.08))

                Canvas { context, size in
                    for speed in curveSnapSpeeds {
                        let y = speedY(speed, height: size.height)
                        var grid = Path(); grid.move(to: CGPoint(x: 0, y: y)); grid.addLine(to: CGPoint(x: size.width, y: y))
                        let major = speed == 1 || speed == 0.2 || speed == 0.5 || speed == 2 || speed == 5 || speed == 10
                        context.stroke(grid, with: .color(.secondary.opacity(major ? 0.24 : 0.10)), lineWidth: major ? 0.8 : 0.5)
                        if major {
                            let label = context.resolve(Text("\(speed, specifier: "%g")×").font(.system(size: 8, design: .monospaced)).foregroundStyle(.secondary))
                            context.draw(label, at: CGPoint(x: 5, y: y - 2), anchor: .bottomLeading)
                        }
                    }

                    var path = Path()
                    for i in 0...220 {
                        let t = Double(i) / 220
                        let p = CGPoint(x: CGFloat(t) * size.width, y: speedY(curve.value(at: t), height: size.height))
                        if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
                    }
                    context.stroke(path, with: .color(.accentColor), lineWidth: 3)

                    for (index, point) in sorted.enumerated() where point.mode != .linear {
                        let base = CGPoint(x: CGFloat(point.t) * size.width, y: speedY(point.speed, height: size.height))
                        if index > 0 {
                            let incoming = CGPoint(x: CGFloat(point.inT) * size.width, y: speedY(point.inSpeed, height: size.height))
                            var guide = Path(); guide.move(to: base); guide.addLine(to: incoming)
                            context.stroke(guide, with: .color(.orange.opacity(point.id == selectedPointID ? 0.95 : 0.38)), lineWidth: point.id == selectedPointID ? 1.5 : 0.8)
                        }
                        if index + 1 < sorted.count {
                            let outgoing = CGPoint(x: CGFloat(point.outT) * size.width, y: speedY(point.outSpeed, height: size.height))
                            var guide = Path(); guide.move(to: base); guide.addLine(to: outgoing)
                            context.stroke(guide, with: .color(.orange.opacity(point.id == selectedPointID ? 0.95 : 0.38)), lineWidth: point.id == selectedPointID ? 1.5 : 0.8)
                        }
                    }
                }
                .allowsHitTesting(false)

                Rectangle()
                    .fill(Color.red.opacity(0.9))
                    .frame(width: 2)
                    .position(x: CGFloat(model.normalizedPlayhead(for: target)) * geo.size.width, y: geo.size.height / 2)
                    .allowsHitTesting(false)

                ForEach(Array(sorted.enumerated()), id: \.element.id) { index, point in
                    if point.mode != .linear {
                        if index > 0 {
                            CurveHandleNodeV44(
                                t: point.inT,
                                speed: point.inSpeed,
                                size: geo.size,
                                coordinateSpaceName: spaceName,
                                onBegin: { selectedPointID = point.id; model.beginCurvePointEdit() },
                                onMove: { t, speed in model.moveCurveHandleInteractive(target, pointID: point.id, side: .incoming, t: t, speed: speed) },
                                onEnd: { model.finishCurvePointEdit(target) }
                            )
                        }
                        if index + 1 < sorted.count {
                            CurveHandleNodeV44(
                                t: point.outT,
                                speed: point.outSpeed,
                                size: geo.size,
                                coordinateSpaceName: spaceName,
                                onBegin: { selectedPointID = point.id; model.beginCurvePointEdit() },
                                onMove: { t, speed in model.moveCurveHandleInteractive(target, pointID: point.id, side: .outgoing, t: t, speed: speed) },
                                onEnd: { model.finishCurvePointEdit(target) }
                            )
                        }
                    }
                }

                ForEach(sorted) { point in
                    CurvePointNodeV44(
                        point: point,
                        selected: point.id == selectedPointID,
                        size: geo.size,
                        coordinateSpaceName: spaceName,
                        onSelect: { selectedPointID = point.id },
                        onBegin: { model.beginCurvePointEdit() },
                        onMove: { t, speed, _ in
                            model.moveCurvePointInteractive(target, pointID: point.id, t: t, speed: speed)
                            model.setCurvePlayheadVisual(target, normalized: t)
                        },
                        onEnd: { t in model.finishCurvePointEdit(target, normalized: t) },
                        onDoubleTap: { model.setCurvePointMode(target, pointID: point.id, mode: .smooth, resetHandles: true) }
                    )
                }

                if let id = selectedPointID, let point = curve.points.first(where: { $0.id == id }) {
                    VStack {
                        HStack {
                            Text(String(format: "%.2f× • %.1f%% • %@", point.speed, point.t * 100, point.mode.rawValue))
                                .font(.caption2.monospacedDigit().weight(.semibold))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                                .background(.ultraThinMaterial, in: Capsule())
                            Spacer()
                        }
                        Spacer()
                    }
                    .padding(8)
                    .allowsHitTesting(false)
                }
            }
            .coordinateSpace(name: spaceName)
            .contentShape(Rectangle())
            .onTapGesture(count: 2, coordinateSpace: .named(spaceName)) { location in
                let t = min(max(Double(location.x / max(1, geo.size.width)), 0.01), 0.99)
                let snap = snappedCurveSpeed(ySpeed(location.y, height: geo.size.height))
                model.addCurvePoint(target, t: t, speed: snap.speed)
                model.seekCurveTarget(target, normalized: t)
            }
        }
    }
}
