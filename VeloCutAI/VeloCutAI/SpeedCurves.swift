import SwiftUI
import Foundation

enum CurveInterpolation: String, CaseIterable, Identifiable, Codable {
    case smooth = "Smooth"
    case linear = "Linear"
    case sharp = "Sharp"
    var id: String { rawValue }
}

enum CurveHandleSide: String, Codable {
    case incoming
    case outgoing
}

enum SpeedFXMode: String, CaseIterable, Identifiable, Codable {
    case multiply = "Multiply"
    case override = "Override"
    var id: String { rawValue }
}

struct SpeedPoint: Identifiable, Equatable, Codable {
    var id: UUID
    var t: Double
    var speed: Double
    var mode: CurveInterpolation
    var inT: Double
    var inSpeed: Double
    var outT: Double
    var outSpeed: Double

    init(
        id: UUID = UUID(),
        t: Double,
        speed: Double,
        mode: CurveInterpolation = .smooth,
        inT: Double? = nil,
        inSpeed: Double? = nil,
        outT: Double? = nil,
        outSpeed: Double? = nil
    ) {
        self.id = id
        self.t = t
        self.speed = clampSpeed(speed)
        self.mode = mode
        self.inT = inT ?? max(0, t - 0.08)
        self.inSpeed = clampSpeed(inSpeed ?? speed)
        self.outT = outT ?? min(1, t + 0.08)
        self.outSpeed = clampSpeed(outSpeed ?? speed)
    }
}

struct SpeedCurve: Equatable, Codable {
    var points: [SpeedPoint]
    // Kept for compatibility with the original v0.4 project. v0.4.4 uses
    // the interpolation mode stored on every point instead.
    var interpolation: CurveInterpolation = .smooth

    static let flat = SpeedCurve(points: [
        SpeedPoint(t: 0, speed: 1, mode: .linear),
        SpeedPoint(t: 1, speed: 1, mode: .linear)
    ])

    func value(at rawT: Double) -> Double {
        let t = min(max(rawT, 0), 1)
        let sorted = points.sorted { $0.t < $1.t }
        guard let first = sorted.first, let last = sorted.last else { return 1 }
        if t <= first.t { return clampSpeed(first.speed) }
        if t >= last.t { return clampSpeed(last.speed) }
        guard let rightIndex = sorted.firstIndex(where: { $0.t >= t }), rightIndex > 0 else { return 1 }

        let a = sorted[rightIndex - 1]
        let b = sorted[rightIndex]
        let span = max(0.0001, b.t - a.t)
        if a.mode == .linear && b.mode == .linear {
            let u = (t - a.t) / span
            return clampSpeed(a.speed + (b.speed - a.speed) * u)
        }

        let c1t = a.mode == .linear ? a.t + span / 3 : min(max(a.outT, a.t), b.t)
        let c2t = b.mode == .linear ? a.t + span * 2 / 3 : min(max(b.inT, a.t), b.t)
        let c1s = a.mode == .linear ? a.speed + (b.speed - a.speed) / 3 : clampSpeed(a.outSpeed)
        let c2s = b.mode == .linear ? a.speed + (b.speed - a.speed) * 2 / 3 : clampSpeed(b.inSpeed)

        var low = 0.0
        var high = 1.0
        var u = (t - a.t) / span
        for _ in 0..<18 {
            u = (low + high) * 0.5
            let x = cubicBezier(a.t, c1t, c2t, b.t, u)
            if x < t { low = u } else { high = u }
        }
        return clampSpeed(cubicBezier(a.speed, c1s, c2s, b.speed, u))
    }

    mutating func normalize() {
        points = points.map {
            SpeedPoint(
                id: $0.id,
                t: min(max($0.t, 0), 1),
                speed: clampSpeed($0.speed),
                mode: $0.mode,
                inT: min(max($0.inT, 0), 1),
                inSpeed: clampSpeed($0.inSpeed),
                outT: min(max($0.outT, 0), 1),
                outSpeed: clampSpeed($0.outSpeed)
            )
        }.sorted { $0.t < $1.t }
        if points.isEmpty { points = SpeedCurve.flat.points }
        if let first = points.first, first.t > 0.001 {
            points.insert(SpeedPoint(t: 0, speed: first.speed, mode: first.mode), at: 0)
        }
        if let last = points.last, last.t < 0.999 {
            points.append(SpeedPoint(t: 1, speed: last.speed, mode: last.mode))
        }
        clampAllHandles()
    }

    mutating func mirror() {
        points = points.map { p in
            SpeedPoint(
                id: p.id,
                t: 1 - p.t,
                speed: p.speed,
                mode: p.mode,
                inT: 1 - p.outT,
                inSpeed: p.outSpeed,
                outT: 1 - p.inT,
                outSpeed: p.inSpeed
            )
        }.sorted { $0.t < $1.t }
        clampAllHandles()
    }

    mutating func movePoint(id: UUID, t: Double, speed: Double) {
        guard let index = points.firstIndex(where: { $0.id == id }) else { return }
        let old = points[index]
        var newT = min(max(t, 0), 1)
        if index == 0 { newT = 0 }
        if index == points.count - 1 { newT = 1 }
        let newSpeed = clampSpeed(speed)
        let dt = newT - old.t
        let ds = newSpeed - old.speed
        points[index].t = newT
        points[index].speed = newSpeed
        points[index].inT += dt
        points[index].outT += dt
        points[index].inSpeed = clampSpeed(points[index].inSpeed + ds)
        points[index].outSpeed = clampSpeed(points[index].outSpeed + ds)
        points.sort { $0.t < $1.t }
        clampAllHandles()
    }

    mutating func addPoint(t: Double, speed: Double? = nil) {
        let safeT = min(max(t, 0.01), 0.99)
        let p = SpeedPoint(t: safeT, speed: speed ?? value(at: safeT), mode: .smooth)
        points.append(p)
        points.sort { $0.t < $1.t }
        resetHandles(pointID: p.id)
    }

    mutating func deletePoint(_ id: UUID) {
        guard points.count > 2, let index = points.firstIndex(where: { $0.id == id }), index != 0, index != points.count - 1 else { return }
        points.remove(at: index)
        clampAllHandles()
    }

    mutating func setPointMode(_ id: UUID, mode: CurveInterpolation, resetHandles: Bool = false) {
        guard let index = points.firstIndex(where: { $0.id == id }) else { return }
        points[index].mode = mode
        if resetHandles || mode == .smooth { resetHandles(pointID: id) }
    }

    mutating func resetHandles(pointID id: UUID) {
        guard let index = points.firstIndex(where: { $0.id == id }) else { return }
        let p = points[index]
        let prevT = index > 0 ? points[index - 1].t : p.t
        let nextT = index + 1 < points.count ? points[index + 1].t : p.t
        let leftSpan = max(0, p.t - prevT)
        let rightSpan = max(0, nextT - p.t)
        let common = max(0.015, min(0.12, min(leftSpan > 0 ? leftSpan / 3 : 0.12, rightSpan > 0 ? rightSpan / 3 : 0.12)))
        points[index].inT = index == 0 ? p.t : max(prevT, p.t - common)
        points[index].outT = index == points.count - 1 ? p.t : min(nextT, p.t + common)
        points[index].inSpeed = p.speed
        points[index].outSpeed = p.speed
        clampAllHandles()
    }

    mutating func moveHandle(pointID id: UUID, side: CurveHandleSide, t: Double, speed: Double) {
        guard let index = points.firstIndex(where: { $0.id == id }) else { return }
        guard points[index].mode != .linear else { return }
        let point = points[index]
        let prevT = index > 0 ? points[index - 1].t : point.t
        let nextT = index + 1 < points.count ? points[index + 1].t : point.t
        let newSpeed = clampSpeed(speed)

        switch side {
        case .incoming:
            guard index > 0 else { return }
            let newT = min(max(t, prevT), point.t)
            points[index].inT = newT
            points[index].inSpeed = newSpeed
            if point.mode == .smooth, index + 1 < points.count {
                let mirroredT = point.t + (point.t - newT)
                points[index].outT = min(max(mirroredT, point.t), nextT)
                points[index].outSpeed = clampSpeed(point.speed + (point.speed - newSpeed))
            }
        case .outgoing:
            guard index + 1 < points.count else { return }
            let newT = min(max(t, point.t), nextT)
            points[index].outT = newT
            points[index].outSpeed = newSpeed
            if point.mode == .smooth, index > 0 {
                let mirroredT = point.t - (newT - point.t)
                points[index].inT = min(max(mirroredT, prevT), point.t)
                points[index].inSpeed = clampSpeed(point.speed + (point.speed - newSpeed))
            }
        }
        clampAllHandles()
    }

    mutating func preparePresetHandles() {
        points.sort { $0.t < $1.t }
        let ids = points.map(\.id)
        for id in ids where points.first(where: { $0.id == id })?.mode != .linear {
            resetHandles(pointID: id)
        }
        clampAllHandles()
    }

    private mutating func clampAllHandles() {
        points.sort { $0.t < $1.t }
        for index in points.indices {
            let p = points[index]
            let prevT = index > 0 ? points[index - 1].t : p.t
            let nextT = index + 1 < points.count ? points[index + 1].t : p.t
            points[index].inT = index == 0 ? p.t : min(max(points[index].inT, prevT), p.t)
            points[index].outT = index == points.count - 1 ? p.t : min(max(points[index].outT, p.t), nextT)
            points[index].inSpeed = clampSpeed(points[index].inSpeed)
            points[index].outSpeed = clampSpeed(points[index].outSpeed)
        }
    }
}

private func cubicBezier(_ p0: Double, _ p1: Double, _ p2: Double, _ p3: Double, _ u: Double) -> Double {
    let v = 1 - u
    return v * v * v * p0 + 3 * v * v * u * p1 + 3 * v * u * u * p2 + u * u * u * p3
}

func clampSpeed(_ value: Double) -> Double { min(max(value, 0.05), 20) }

let curveSnapSpeeds: [Double] = [0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 10, 15, 20]

func snappedCurveSpeed(_ raw: Double, threshold: Double = 0.026) -> (speed: Double, snapped: Double?) {
    let safe = clampSpeed(raw)
    let minS = 0.05
    let maxS = 20.0
    let norm: (Double) -> Double = { (log(clampSpeed($0)) - log(minS)) / (log(maxS) - log(minS)) }
    guard let closest = curveSnapSpeeds.min(by: { abs(norm($0) - norm(safe)) < abs(norm($1) - norm(safe)) }) else { return (safe, nil) }
    if abs(norm(closest) - norm(safe)) <= threshold { return (closest, closest) }
    return (safe, nil)
}

struct SpeedCurvePreset: Identifiable, Equatable {
    let id: String
    let name: String
    let category: String
    let curve: SpeedCurve

    static let all: [SpeedCurvePreset] = [
        .init(id: "velocity", name: "Velocity", category: "Trending", curve: curve([(0,1),(0.22,1),(0.38,0.25),(0.52,5.2),(0.70,0.45),(1,1)])),
        .init(id: "tiktok", name: "TikTok Ramp", category: "Trending", curve: curve([(0,1),(0.18,1),(0.34,0.4),(0.49,8),(0.63,0.35),(0.82,1),(1,1)])),
        .init(id: "flash", name: "Flash Ramp", category: "Impact", curve: curve([(0,1),(0.36,1),(0.48,10),(0.57,0.2),(0.74,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.smooth,.linear])),
        .init(id: "anime", name: "Anime Impact", category: "Anime/AMV", curve: curve([(0,1),(0.28,1),(0.42,0.15),(0.54,6.5),(0.67,0.3),(0.84,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "amv", name: "AMV Smooth", category: "Anime/AMV", curve: curve([(0,1),(0.22,0.55),(0.50,3.2),(0.78,0.55),(1,1)])),
        .init(id: "whip", name: "Whip", category: "Transition", curve: curve([(0,1),(0.38,1),(0.50,12),(0.64,1),(1,1)], modes: [.linear,.smooth,.sharp,.smooth,.linear])),
        .init(id: "punch", name: "Punch", category: "Impact", curve: curve([(0,1),(0.40,0.2),(0.52,7),(0.68,1),(1,1)], modes: [.linear,.sharp,.sharp,.smooth,.linear])),
        .init(id: "zoomhit", name: "Zoom Hit", category: "Impact", curve: curve([(0,1),(0.28,0.35),(0.48,5),(0.66,0.35),(0.82,1),(1,1)])),
        .init(id: "beatdrop", name: "Beat Drop", category: "Trending", curve: curve([(0,1),(0.25,0.7),(0.44,0.2),(0.53,8),(0.66,1.6),(0.82,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "velocitypro", name: "Velocity Pro", category: "Trending", curve: curve([(0,1),(0.16,0.55),(0.29,4.5),(0.40,0.22),(0.52,8.5),(0.65,0.32),(0.79,3.4),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "micro", name: "Micro Hit", category: "Impact", curve: curve([(0,1),(0.44,1),(0.49,5.5),(0.56,0.45),(0.66,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.smooth,.linear])),
        .init(id: "smoothpush", name: "Smooth Push", category: "Smooth", curve: curve([(0,1),(0.22,0.75),(0.50,2.4),(0.78,0.75),(1,1)])),

        // v0.4.4 transition-focused presets with per-point interpolation.
        .init(id: "whipTransition", name: "Whip Transition", category: "Transitions", curve: curve([(0,1),(0.25,1),(0.43,2),(0.52,12),(0.61,3),(0.78,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "flashCut", name: "Flash Cut", category: "Transitions", curve: curve([(0,1),(0.30,1),(0.42,0.25),(0.50,15),(0.57,0.2),(0.72,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "zoomImpactTransition", name: "Zoom Impact", category: "Transitions", curve: curve([(0,1),(0.26,0.35),(0.48,7),(0.66,0.35),(0.82,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.smooth,.linear])),
        .init(id: "animeCut", name: "Anime Cut", category: "Transitions", curve: curve([(0,1),(0.24,1),(0.38,0.15),(0.49,8),(0.60,0.25),(0.71,4),(0.84,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "velocitySwipe", name: "Velocity Swipe", category: "Transitions", curve: curve([(0,1),(0.20,0.5),(0.38,5),(0.50,12),(0.62,0.4),(0.80,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "hardImpact", name: "Hard Impact", category: "Transitions", curve: curve([(0,1),(0.34,1),(0.45,0.2),(0.51,10),(0.60,1),(1,1)], modes: [.linear,.linear,.sharp,.sharp,.smooth,.linear])),
        .init(id: "cameraWhip", name: "Camera Whip", category: "Transitions", curve: curve([(0,1),(0.28,1.5),(0.48,15),(0.64,1.5),(0.82,1),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.smooth,.linear])),
        .init(id: "beatFlash", name: "Beat Flash", category: "Transitions", curve: curve([(0,1),(0.41,1),(0.47,0.2),(0.51,12),(0.57,0.3),(0.66,1),(1,1)], modes: [.linear,.linear,.sharp,.sharp,.sharp,.smooth,.linear])),
        .init(id: "amvTransitionPro", name: "AMV Transition Pro", category: "Transitions", curve: curve([(0,1),(0.16,0.6),(0.29,4),(0.39,0.2),(0.50,10),(0.61,0.3),(0.74,5),(0.87,0.7),(1,1)], modes: [.linear,.smooth,.sharp,.sharp,.sharp,.sharp,.sharp,.smooth,.linear]))
    ]

    static func named(_ id: String) -> SpeedCurvePreset { all.first(where: { $0.id == id }) ?? all[1] }

    private static func curve(_ values: [(Double, Double)], modes: [CurveInterpolation]? = nil) -> SpeedCurve {
        var curve = SpeedCurve(points: values.enumerated().map { index, value in
            SpeedPoint(t: value.0, speed: value.1, mode: modes?[safe: index] ?? .smooth)
        })
        curve.preparePresetHandles()
        return curve
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? { indices.contains(index) ? self[index] : nil }
}

struct GlobalSpeedFX: Identifiable, Equatable, Codable {
    var id: UUID = UUID()
    var name: String
    var start: Double
    var duration: Double
    var curve: SpeedCurve
    var strength: Double = 1
    var mode: SpeedFXMode = .multiply
    var isEnabled: Bool = true

    var end: Double { start + max(0.08, duration) }

    func factor(at projectTime: Double) -> Double? {
        guard isEnabled, projectTime >= start, projectTime <= end else { return nil }
        let n = (projectTime - start) / max(0.08, duration)
        let raw = curve.value(at: n)
        return clampSpeed(1 + (raw - 1) * strength)
    }
}

enum CurveTarget: Identifiable, Equatable {
    case clip(UUID)
    case global(UUID)
    var id: String {
        switch self {
        case .clip(let id): return "clip-\(id.uuidString)"
        case .global(let id): return "global-\(id.uuidString)"
        }
    }
}

struct CurveThumbnail: View {
    let curve: SpeedCurve
    var lineWidth: CGFloat = 2
    var body: some View {
        Canvas { context, size in
            guard size.width > 1, size.height > 1 else { return }
            var path = Path()
            for i in 0...60 {
                let t = Double(i) / 60
                let x = CGFloat(t) * size.width
                let y = speedY(curve.value(at: t), height: size.height)
                if i == 0 { path.move(to: CGPoint(x: x, y: y)) }
                else { path.addLine(to: CGPoint(x: x, y: y)) }
            }
            context.stroke(path, with: .color(.accentColor), lineWidth: lineWidth)
        }
    }
}

// Lightweight generic curve view kept for compatibility. The v0.4.4 editor
// uses the richer graph in VeloCutV4Enhancements.swift.
struct InteractiveCurveView: View {
    let curve: SpeedCurve
    let selectedPointID: UUID?
    let onSelect: (UUID) -> Void
    let onMove: (UUID, Double, Double) -> Void
    let onAdd: (Double, Double) -> Void

    var body: some View {
        GeometryReader { geo in
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.secondary.opacity(0.08))
                CurveThumbnail(curve: curve, lineWidth: 3).padding(.vertical, 1)
                ForEach(curve.points) { point in
                    Circle()
                        .fill(point.id == selectedPointID ? Color.white : Color.accentColor)
                        .overlay(Circle().stroke(Color.accentColor, lineWidth: 2))
                        .frame(width: point.id == selectedPointID ? 18 : 14, height: point.id == selectedPointID ? 18 : 14)
                        .position(x: CGFloat(point.t) * geo.size.width, y: speedY(point.speed, height: geo.size.height))
                        .contentShape(Rectangle().inset(by: -12))
                        .onTapGesture { onSelect(point.id) }
                        .gesture(DragGesture(minimumDistance: 2).onChanged { value in
                            onSelect(point.id)
                            let t = min(max(Double(value.location.x / max(1, geo.size.width)), 0), 1)
                            let snap = snappedCurveSpeed(ySpeed(value.location.y, height: geo.size.height))
                            onMove(point.id, t, snap.speed)
                        })
                }
            }
            .contentShape(Rectangle())
            .onTapGesture(count: 2) { location in
                let t = min(max(Double(location.x / max(1, geo.size.width)), 0.01), 0.99)
                onAdd(t, snappedCurveSpeed(ySpeed(location.y, height: geo.size.height)).speed)
            }
        }
    }
}

func speedY(_ speed: Double, height: CGFloat) -> CGFloat {
    let minS = 0.05, maxS = 20.0
    let n = (log(clampSpeed(speed)) - log(minS)) / (log(maxS) - log(minS))
    return height * CGFloat(1 - n)
}

func ySpeed(_ y: CGFloat, height: CGFloat) -> Double {
    let minS = 0.05, maxS = 20.0
    let n = 1 - Double(min(max(y / max(1, height), 0), 1))
    return clampSpeed(exp(log(minS) + n * (log(maxS) - log(minS))))
}
