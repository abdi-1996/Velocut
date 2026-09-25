import SwiftUI
import AVKit
import AVFoundation
import UniformTypeIdentifiers
import UIKit
import CoreImage
import PhotosUI
import CoreTransferable

enum EditorFilter: String, CaseIterable, Identifiable {
    case original = "Оригинал", vivid = "Яркий", mono = "Ч/Б", cinematic = "Кино", warm = "Тёплый", cool = "Холодный"
    var id: String { rawValue }
}

enum ExportQuality: String, CaseIterable, Identifiable {
    case hd = "720p", fullHD = "1080p", ultraHD = "4K"
    var id: String { rawValue }
    var presetName: String {
        switch self {
        case .hd: return AVAssetExportPreset1280x720
        case .fullHD: return AVAssetExportPreset1920x1080
        case .ultraHD: return AVAssetExportPreset3840x2160
        }
    }
}

enum InspectorTool: String, Identifiable { case trim, speed, audio, text, filters, adjust, enhance, export; var id: String { rawValue } }

enum PlaybackMode: String, CaseIterable, Identifiable {
    case project = "Проект", clip = "Клип", loopClip = "Цикл клипа"
    var id: String { rawValue }
    var icon: String { self == .project ? "play.rectangle.on.rectangle" : (self == .clip ? "play.square" : "repeat.1") }
}

struct PickedMovie: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { SentTransferredFile($0.url) } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let dst = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-Photo-\(UUID().uuidString).\(ext)")
            try? FileManager.default.removeItem(at: dst)
            try FileManager.default.copyItem(at: received.file, to: dst)
            return PickedMovie(url: dst)
        }
    }
}

struct EditorClip: Identifiable, Equatable {
    let id: UUID
    let url: URL
    var name: String
    var duration: Double
    var trimStart: Double
    var trimEnd: Double
    var baseSpeed: Double
    var volume: Double
    var track: Int
    var curveEnabled: Bool
    var speedCurve: SpeedCurve

    init(id: UUID = UUID(), url: URL, name: String, duration: Double, trimStart: Double, trimEnd: Double, baseSpeed: Double = 1, volume: Double = 1, track: Int = 0, curveEnabled: Bool = false, speedCurve: SpeedCurve = .flat) {
        self.id = id; self.url = url; self.name = name; self.duration = duration; self.trimStart = trimStart; self.trimEnd = trimEnd
        self.baseSpeed = baseSpeed; self.volume = volume; self.track = track; self.curveEnabled = curveEnabled; self.speedCurve = speedCurve
    }
    var sourceDuration: Double { max(0.05, trimEnd - trimStart) }
}

struct ClipLayout: Identifiable {
    let id: UUID
    let clip: EditorClip
    let start: Double
    let duration: Double
    var end: Double { start + duration }
}

private struct ProjectSnapshot {
    var clips: [EditorClip]
    var speedFX: [GlobalSpeedFX]
    var selectedClipID: UUID?
    var overlayText: String
    var filter: EditorFilter
    var brightness: Double
    var contrast: Double
    var saturation: Double
    var enhance: Double
}

@MainActor
final class EditorViewModel: ObservableObject {
    @Published var clips: [EditorClip] = []
    @Published var speedFX: [GlobalSpeedFX] = []
    @Published var selectedClipID: UUID?
    @Published var player = AVPlayer()
    @Published var projectTime: Double = 0
    @Published var isPlaying = false
    @Published var isFileImporting = false
    @Published var isAudioImporting = false
    @Published var isExporting = false
    @Published var exportProgress = 0.0
    @Published var exportedURL: URL?
    @Published var errorMessage: String?
    @Published var timelineZoom = 1.0
    @Published var playbackMode: PlaybackMode = .project
    @Published var returnPlayheadAfterStop = true
    @Published var isPreviewCaching = false
    @Published var cacheRevision = 0
    @Published var selectedFilter: EditorFilter = .original
    @Published var brightness = 0.0
    @Published var contrast = 1.0
    @Published var saturation = 1.0
    @Published var enhanceAmount = 0.0
    @Published var overlayText = ""
    @Published var overlayTextSize = 36.0
    @Published var overlayTextY = 0.82
    @Published var musicURL: URL?
    @Published var musicName: String?
    @Published var musicVolume = 0.8
    @Published var exportQuality: ExportQuality = .fullHD

    private var observer: Any?
    private var undoStack: [ProjectSnapshot] = []
    private var redoStack: [ProjectSnapshot] = []
    private var assetCache: [URL: AVURLAsset] = [:]
    private var rebuildTask: Task<Void, Never>?
    private var exportTimer: Timer?
    private var playbackStart = 0.0
    private var playbackClipID: UUID?
    private var scrubbing = false

    init() {
        player.automaticallyWaitsToMinimizeStalling = false
        observer = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.033, preferredTimescale: 600), queue: .main) { [weak self] time in
            guard let self else { return }
            Task { @MainActor in
                guard !self.scrubbing else { return }
                self.projectTime = min(max(0, CMTimeGetSeconds(time)), self.projectDuration)
                self.isPlaying = self.player.rate != 0
                self.enforcePlaybackBoundary()
                if self.playbackMode == .project || !self.isPlaying { self.syncSelectionForProjectTime() }
            }
        }
    }

    var selectedClip: EditorClip? { clips.first(where: { $0.id == selectedClipID }) }
    var selectedIndex: Int? { selectedClipID.flatMap { id in clips.firstIndex(where: { $0.id == id }) } }
    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }
    var layouts: [ClipLayout] { makeLayouts() }
    var projectDuration: Double { layouts.last?.end ?? 0 }

    func asset(for url: URL) -> AVURLAsset {
        if let a = assetCache[url] { return a }
        let a = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        assetCache[url] = a
        return a
    }

    func importVideos(_ urls: [URL]) {
        Task {
            var newClips: [EditorClip] = []
            for url in urls {
                do {
                    let d = max(0.1, CMTimeGetSeconds(try await asset(for: url).load(.duration)))
                    newClips.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: d, trimStart: 0, trimEnd: d))
                } catch { errorMessage = "Не удалось открыть видео: \(error.localizedDescription)" }
            }
            guard !newClips.isEmpty else { return }
            registerUndo(); clips.append(contentsOf: newClips)
            if selectedClipID == nil { selectedClipID = newClips.first?.id }
            schedulePreview(immediate: true)
        }
    }

    func importMusic(_ url: URL) { musicURL = url; musicName = url.deletingPathExtension().lastPathComponent; schedulePreview() }

    private func localSpeed(_ clip: EditorClip, normalized: Double) -> Double {
        clampSpeed(clip.baseSpeed * (clip.curveEnabled ? clip.speedCurve.value(at: normalized) : 1))
    }

    private func effectiveSpeed(local: Double, at time: Double) -> Double {
        var value = local
        for fx in speedFX where fx.isEnabled {
            guard let factor = fx.factor(at: time) else { continue }
            switch fx.mode {
            case .multiply: value *= factor
            case .override: value = factor
            }
        }
        return clampSpeed(value)
    }

    private func simulatedDuration(of clip: EditorClip, startingAt start: Double) -> Double {
        let segments = (clip.curveEnabled || !speedFX.isEmpty) ? 64 : 1
        let ds = clip.sourceDuration / Double(segments)
        var cursor = start
        for i in 0..<segments {
            let n = (Double(i) + 0.5) / Double(segments)
            let speed = effectiveSpeed(local: localSpeed(clip, normalized: n), at: cursor)
            cursor += ds / speed
        }
        return max(0.01, cursor - start)
    }

    private func makeLayouts() -> [ClipLayout] {
        var cursor = 0.0
        return clips.map { clip in
            let d = simulatedDuration(of: clip, startingAt: cursor)
            defer { cursor += d }
            return ClipLayout(id: clip.id, clip: clip, start: cursor, duration: d)
        }
    }

    func layout(for id: UUID) -> ClipLayout? { layouts.first(where: { $0.id == id }) }
    func projectStart(of id: UUID) -> Double { layout(for: id)?.start ?? 0 }

    private func clipAt(_ time: Double) -> ClipLayout? {
        let list = layouts
        guard !list.isEmpty else { return nil }
        return list.first(where: { time >= $0.start && time < $0.end }) ?? list.last
    }

    func selectClip(_ id: UUID, seek: Bool = true) { selectedClipID = id; if seek { seekProject(to: projectStart(of: id), exact: true) } }
    func syncSelectionForProjectTime() { if let l = clipAt(projectTime), selectedClipID != l.id { selectedClipID = l.id } }

    func beginScrub() { scrubbing = true; player.pause(); isPlaying = false }
    func scrub(to t: Double) { projectTime = min(max(0, t), projectDuration); syncSelectionForProjectTime(); seekProject(to: projectTime, exact: true) }
    func endScrub() { scrubbing = false; seekProject(to: projectTime, exact: true) }
    func seek(by delta: Double) { beginScrub(); scrub(to: projectTime + delta); endScrub() }

    func seekProject(to t: Double, exact: Bool = false) {
        let safe = min(max(0, t), projectDuration); projectTime = safe
        let time = CMTime(seconds: safe, preferredTimescale: 600)
        if exact { player.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero) }
        else { player.seek(to: time, toleranceBefore: CMTime(seconds: 0.03, preferredTimescale: 600), toleranceAfter: CMTime(seconds: 0.03, preferredTimescale: 600)) }
    }

    func playPause() {
        guard !clips.isEmpty else { return }
        if player.rate != 0 { stopPlayback(); return }
        playbackStart = projectTime
        playbackClipID = selectedClipID ?? clipAt(projectTime)?.id
        if playbackMode == .project, projectTime >= projectDuration - 0.03 { seekProject(to: 0, exact: true); playbackStart = 0 }
        if playbackMode != .project, let id = playbackClipID, let l = layout(for: id), (projectTime < l.start || projectTime >= l.end - 0.03) { seekProject(to: l.start, exact: true); playbackStart = l.start }
        player.play(); isPlaying = true
    }

    private func stopPlayback() { player.pause(); isPlaying = false; if returnPlayheadAfterStop { seekProject(to: playbackStart, exact: true) } }

    private func enforcePlaybackBoundary() {
        guard player.rate != 0 else { return }
        if playbackMode == .project {
            if projectTime >= projectDuration - 0.02 { player.pause(); isPlaying = false; if returnPlayheadAfterStop { seekProject(to: playbackStart, exact: true) } }
        } else if let id = playbackClipID, let l = layout(for: id), projectTime >= l.end - 0.02 {
            if playbackMode == .loopClip { seekProject(to: l.start, exact: true); player.play() }
            else { player.pause(); isPlaying = false; seekProject(to: returnPlayheadAfterStop ? playbackStart : l.end, exact: true) }
        }
    }

    func setBaseSpeed(_ speed: Double) { mutateSelected { $0.baseSpeed = clampSpeed(speed) } }
    func setVolume(_ volume: Double) { mutateSelected { $0.volume = min(max(volume, 0), 2) } }
    func setTrimStart(_ v: Double) { mutateSelected { $0.trimStart = min(max(0, v), $0.trimEnd - 0.05) } }
    func setTrimEnd(_ v: Double) { mutateSelected { $0.trimEnd = max(min($0.duration, v), $0.trimStart + 0.05) } }

    private func mutateSelected(_ body: (inout EditorClip) -> Void) {
        guard let i = selectedIndex else { return }; registerUndo(); body(&clips[i]); projectTime = min(projectTime, projectDuration); schedulePreview()
    }

    func splitAtPlayhead() {
        guard let l = clipAt(projectTime), let index = clips.firstIndex(where: { $0.id == l.id }), let sourceTime = sourceTime(in: l, at: projectTime) else { return }
        let clip = clips[index]
        guard sourceTime > clip.trimStart + 0.08, sourceTime < clip.trimEnd - 0.08 else { haptic(.error); return }
        registerUndo()
        var left = clip; left.trimEnd = sourceTime
        let right = EditorClip(url: clip.url, name: clip.name, duration: clip.duration, trimStart: sourceTime, trimEnd: clip.trimEnd, baseSpeed: clip.baseSpeed, volume: clip.volume, track: clip.track, curveEnabled: clip.curveEnabled, speedCurve: clip.speedCurve)
        clips[index] = left; clips.insert(right, at: index + 1); selectedClipID = right.id
        schedulePreview(immediate: true); haptic(.medium)
    }

    private func sourceTime(in layout: ClipLayout, at target: Double) -> Double? {
        let clip = layout.clip, segments = 96, ds = clip.sourceDuration / Double(segments)
        var cursor = layout.start
        for i in 0..<segments {
            let n = (Double(i) + 0.5) / Double(segments)
            let speed = effectiveSpeed(local: localSpeed(clip, normalized: n), at: cursor)
            let out = ds / speed
            if target <= cursor + out {
                let f = min(max((target - cursor) / max(out, 0.0001), 0), 1)
                return clip.trimStart + (Double(i) + f) * ds
            }
            cursor += out
        }
        return clip.trimEnd
    }

    func duplicateClip(_ id: UUID) {
        guard let i = clips.firstIndex(where: { $0.id == id }) else { return }; registerUndo(); let c = clips[i]
        clips.insert(EditorClip(url: c.url, name: c.name + " copy", duration: c.duration, trimStart: c.trimStart, trimEnd: c.trimEnd, baseSpeed: c.baseSpeed, volume: c.volume, track: c.track, curveEnabled: c.curveEnabled, speedCurve: c.speedCurve), at: i + 1)
        schedulePreview(immediate: true)
    }

    func duplicateClipAsNew(_ id: UUID) {
        guard let i = clips.firstIndex(where: { $0.id == id }) else { return }; let c = clips[i]
        Task { do {
            let ext = c.url.pathExtension.isEmpty ? "mov" : c.url.pathExtension
            let dst = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-New-\(UUID().uuidString).\(ext)")
            try FileManager.default.copyItem(at: c.url, to: dst); registerUndo()
            clips.insert(EditorClip(url: dst, name: c.name + " new", duration: c.duration, trimStart: c.trimStart, trimEnd: c.trimEnd, baseSpeed: c.baseSpeed, volume: c.volume, track: c.track, curveEnabled: c.curveEnabled, speedCurve: c.speedCurve), at: i + 1)
            schedulePreview(immediate: true)
        } catch { errorMessage = error.localizedDescription } }
    }

    func deleteClip(_ id: UUID) { guard let i = clips.firstIndex(where: { $0.id == id }) else { return }; registerUndo(); clips.remove(at: i); selectedClipID = clips.first?.id; projectTime = min(projectTime, projectDuration); schedulePreview(immediate: true) }

    func moveClip(_ id: UUID, translation: CGSize, pps: Double) {
        guard let i = clips.firstIndex(where: { $0.id == id }) else { return }
        let horizontal = Int((translation.width / max(70, pps * 1.2)).rounded()), vertical = Int((translation.height / 52).rounded())
        guard horizontal != 0 || vertical != 0 else { return }; registerUndo(); var c = clips.remove(at: i); c.track = min(2, max(0, c.track + vertical)); clips.insert(c, at: min(clips.count, max(0, i + horizontal))); selectedClipID = c.id; schedulePreview(immediate: true)
    }

    // MARK: Curves
    func curve(for target: CurveTarget) -> SpeedCurve {
        switch target {
        case .clip(let id): return clips.first(where: { $0.id == id })?.speedCurve ?? .flat
        case .global(let id): return speedFX.first(where: { $0.id == id })?.curve ?? .flat
        }
    }

    func applyPreset(_ preset: SpeedCurvePreset, to target: CurveTarget) {
        registerUndo()
        switch target {
        case .clip(let id): if let i = clips.firstIndex(where: { $0.id == id }) { clips[i].speedCurve = preset.curve; clips[i].curveEnabled = true }
        case .global(let id): if let i = speedFX.firstIndex(where: { $0.id == id }) { speedFX[i].curve = preset.curve; speedFX[i].name = preset.name }
        }
        schedulePreview()
    }

    func setCurveEnabled(_ id: UUID, _ enabled: Bool) { guard let i = clips.firstIndex(where: { $0.id == id }) else { return }; registerUndo(); clips[i].curveEnabled = enabled; schedulePreview() }
    func setCurveInterpolation(_ target: CurveTarget, _ interpolation: CurveInterpolation) { updateCurve(target) { $0.interpolation = interpolation } }
    func mirrorCurve(_ target: CurveTarget) { updateCurve(target) { $0.mirror() } }
    func moveCurvePoint(_ target: CurveTarget, pointID: UUID, t: Double, speed: Double) { updateCurve(target, register: false) { $0.movePoint(id: pointID, t: t, speed: speed) } }
    func addCurvePoint(_ target: CurveTarget, t: Double, speed: Double? = nil) { updateCurve(target) { $0.addPoint(t: t, speed: speed) } }
    func deleteCurvePoint(_ target: CurveTarget, pointID: UUID) { updateCurve(target) { $0.deletePoint(pointID) } }

    private func updateCurve(_ target: CurveTarget, register: Bool = true, body: (inout SpeedCurve) -> Void) {
        if register { registerUndo() }
        switch target {
        case .clip(let id): if let i = clips.firstIndex(where: { $0.id == id }) { body(&clips[i].speedCurve); clips[i].curveEnabled = true }
        case .global(let id): if let i = speedFX.firstIndex(where: { $0.id == id }) { body(&speedFX[i].curve) }
        }
        schedulePreview()
    }

    func normalizedPlayhead(for target: CurveTarget) -> Double {
        switch target {
        case .clip(let id): guard let l = layout(for: id) else { return 0.5 }; return min(max((projectTime - l.start) / max(l.duration, 0.01), 0), 1)
        case .global(let id): guard let fx = speedFX.first(where: { $0.id == id }) else { return 0.5 }; return min(max((projectTime - fx.start) / max(fx.duration, 0.08), 0), 1)
        }
    }

    func addSpeedFX(preset: SpeedCurvePreset, at time: Double? = nil) {
        registerUndo(); let start = min(max(0, time ?? projectTime), max(0, projectDuration)); speedFX.append(GlobalSpeedFX(name: preset.name, start: start, duration: 0.8, curve: preset.curve)); schedulePreview()
    }
    func deleteSpeedFX(_ id: UUID) { registerUndo(); speedFX.removeAll { $0.id == id }; schedulePreview() }
    func duplicateSpeedFX(_ id: UUID, atPlayhead: Bool = false) { guard let fx = speedFX.first(where: { $0.id == id }) else { return }; registerUndo(); var c = fx; c.id = UUID(); c.start = atPlayhead ? projectTime : fx.end + 0.06; speedFX.append(c); schedulePreview() }
    func repeatSpeedFX(_ id: UUID, count: Int) { guard let fx = speedFX.first(where: { $0.id == id }), count > 1 else { return }; registerUndo(); for n in 1..<count { var c = fx; c.id = UUID(); c.start = fx.start + Double(n) * (fx.duration + 0.06); speedFX.append(c) }; schedulePreview() }
    func moveSpeedFX(_ id: UUID, delta: Double) { guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }; registerUndo(); speedFX[i].start = max(0, speedFX[i].start + delta); schedulePreview() }
    func setSpeedFXStrength(_ id: UUID, _ value: Double) { guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }; speedFX[i].strength = min(max(value, 0, ), 2); schedulePreview() }
    func setSpeedFXDuration(_ id: UUID, _ value: Double) { guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }; speedFX[i].duration = min(max(value, 0.08), 8); schedulePreview() }
    func setSpeedFXMode(_ id: UUID, _ mode: SpeedFXMode) { guard let i = speedFX.firstIndex(where: { $0.id == id }) else { return }; speedFX[i].mode = mode; schedulePreview() }

    // MARK: Color / undo
    func setFilter(_ f: EditorFilter) { registerUndo(); selectedFilter = f; schedulePreview() }
    func updateColor(brightness b: Double? = nil, contrast c: Double? = nil, saturation s: Double? = nil) { if let b { brightness = b }; if let c { contrast = c }; if let s { saturation = s }; schedulePreview() }
    func setEnhance(_ v: Double) { enhanceAmount = v; schedulePreview() }

    func registerUndo() { undoStack.append(snapshot()); if undoStack.count > 40 { undoStack.removeFirst() }; redoStack.removeAll(); objectWillChange.send() }
    func undo() { guard let s = undoStack.popLast() else { return }; redoStack.append(snapshot()); restore(s) }
    func redo() { guard let s = redoStack.popLast() else { return }; undoStack.append(snapshot()); restore(s) }
    private func snapshot() -> ProjectSnapshot { ProjectSnapshot(clips: clips, speedFX: speedFX, selectedClipID: selectedClipID, overlayText: overlayText, filter: selectedFilter, brightness: brightness, contrast: contrast, saturation: saturation, enhance: enhanceAmount) }
    private func restore(_ s: ProjectSnapshot) { clips = s.clips; speedFX = s.speedFX; selectedClipID = s.selectedClipID; overlayText = s.overlayText; selectedFilter = s.filter; brightness = s.brightness; contrast = s.contrast; saturation = s.saturation; enhanceAmount = s.enhance; projectTime = min(projectTime, projectDuration); schedulePreview(immediate: true) }

    // MARK: Preview / export
    func schedulePreview(immediate: Bool = false) {
        rebuildTask?.cancel(); isPreviewCaching = true; let target = min(projectTime, projectDuration)
        rebuildTask = Task { [weak self] in
            if !immediate { try? await Task.sleep(nanoseconds: 110_000_000) }
            guard !Task.isCancelled, let self else { return }; await self.rebuildPreview(target: target)
        }
    }

    private func rebuildPreview(target: Double) async {
        guard !clips.isEmpty else { player.replaceCurrentItem(with: nil); isPreviewCaching = false; return }
        do {
            let (composition, mix) = try await buildComposition(clips, includeMusic: true)
            let item = AVPlayerItem(asset: composition); item.preferredForwardBufferDuration = 1.2; item.audioMix = mix; item.videoComposition = makeVideoComposition(asset: composition, includeText: false)
            player.replaceCurrentItem(with: item); let safe = min(max(0, target), CMTimeGetSeconds(composition.duration)); projectTime = safe
            await player.seek(to: CMTime(seconds: safe, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            cacheRevision += 1; isPreviewCaching = false
        } catch { isPreviewCaching = false; errorMessage = "Ошибка кеша: \(error.localizedDescription)" }
    }

    private func buildComposition(_ sourceClips: [EditorClip], includeMusic: Bool) async throws -> (AVMutableComposition, AVMutableAudioMix) {
        let composition = AVMutableComposition()
        guard let video = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else { throw NSError(domain: "VeloCut", code: 1, userInfo: [NSLocalizedDescriptionKey: "Нет видеодорожки"]) }
        let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        let audioParams = audio.map { AVMutableAudioMixInputParameters(track: $0) }
        var cursor = CMTime.zero; var firstTransform: CGAffineTransform?

        for clip in sourceClips {
            let a = asset(for: clip.url); guard let srcV = try await a.loadTracks(withMediaType: .video).first else { continue }
            if firstTransform == nil { firstTransform = try await srcV.load(.preferredTransform) }
            let srcA = try await a.loadTracks(withMediaType: .audio).first
            let segments = (clip.curveEnabled || !speedFX.isEmpty) ? 48 : 1
            let ds = clip.sourceDuration / Double(segments)
            for i in 0..<segments {
                let n = (Double(i) + 0.5) / Double(segments)
                let cursorSeconds = CMTimeGetSeconds(cursor)
                let speed = effectiveSpeed(local: localSpeed(clip, normalized: n), at: cursorSeconds)
                let range = CMTimeRange(start: CMTime(seconds: clip.trimStart + Double(i) * ds, preferredTimescale: 6000), duration: CMTime(seconds: ds, preferredTimescale: 6000))
                try video.insertTimeRange(range, of: srcV, at: cursor)
                if let srcA, let audio { try? audio.insertTimeRange(range, of: srcA, at: cursor) }
                let inserted = CMTimeRange(start: cursor, duration: CMTime(seconds: ds, preferredTimescale: 6000))
                let out = CMTime(seconds: ds / speed, preferredTimescale: 6000)
                video.scaleTimeRange(inserted, toDuration: out); if let audio { audio.scaleTimeRange(inserted, toDuration: out) }
                audioParams?.setVolume(Float(clip.volume), at: cursor); cursor = cursor + out
            }
        }
        if let firstTransform { video.preferredTransform = firstTransform }

        var musicParams: AVMutableAudioMixInputParameters?
        if includeMusic, let musicURL, let musicTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid), let src = try await asset(for: musicURL).loadTracks(withMediaType: .audio).first {
            let total = CMTimeGetSeconds(cursor), musicDuration = CMTimeGetSeconds(try await asset(for: musicURL).load(.duration)), d = min(total, musicDuration)
            if d > 0.05 { try? musicTrack.insertTimeRange(CMTimeRange(start: .zero, duration: CMTime(seconds: d, preferredTimescale: 600)), of: src, at: .zero); let p = AVMutableAudioMixInputParameters(track: musicTrack); p.setVolume(Float(musicVolume), at: .zero); musicParams = p }
        }
        let mix = AVMutableAudioMix(); mix.inputParameters = [audioParams, musicParams].compactMap { $0 }; return (composition, mix)
    }

    nonisolated private static func applyLook(_ source: CIImage, filter: EditorFilter, brightness: Double, contrast: Double, saturation: Double, enhance: Double) -> CIImage {
        let extent = source.extent; var image = source.clampedToExtent()
        switch filter {
        case .original: break
        case .vivid: image = image.applyingFilter("CIVibrance", parameters: ["inputAmount":0.4]).applyingFilter("CIColorControls", parameters:[kCIInputSaturationKey:1.25,kCIInputContrastKey:1.08])
        case .mono: image = image.applyingFilter("CIPhotoEffectNoir")
        case .cinematic: image = image.applyingFilter("CIColorControls", parameters:[kCIInputSaturationKey:0.82,kCIInputContrastKey:1.16])
        case .warm: image = image.applyingFilter("CITemperatureAndTint", parameters:["inputNeutral":CIVector(x:6500,y:0),"inputTargetNeutral":CIVector(x:5000,y:0)])
        case .cool: image = image.applyingFilter("CITemperatureAndTint", parameters:["inputNeutral":CIVector(x:6500,y:0),"inputTargetNeutral":CIVector(x:8000,y:0)])
        }
        image = image.applyingFilter("CIColorControls", parameters:[kCIInputBrightnessKey:brightness,kCIInputContrastKey:contrast,kCIInputSaturationKey:saturation])
        if enhance > 0 { image = image.applyingFilter("CINoiseReduction", parameters:["inputNoiseLevel":0.015 + enhance*0.045,"inputSharpness":0.4 + enhance*0.4]).applyingFilter("CISharpenLuminance", parameters:[kCIInputSharpnessKey:enhance*0.7]) }
        return image.cropped(to: extent)
    }

    nonisolated private static func addText(_ base: CIImage, text: String, size: Double, y: Double) -> CIImage {
        guard !text.isEmpty, let f = CIFilter(name: "CITextImageGenerator") else { return base }; f.setValue(text, forKey:"inputText"); f.setValue("HelveticaNeue-Bold", forKey:"inputFontName"); f.setValue(size * max(1, base.extent.width/1080), forKey:"inputFontSize"); guard let ti = f.outputImage else { return base }
        let x = base.extent.midX - ti.extent.width/2; let yy = max(0, min(base.extent.height-ti.extent.height, base.extent.height*CGFloat(1-y)-ti.extent.height/2)); return ti.transformed(by:CGAffineTransform(translationX:x-ti.extent.minX,y:yy-ti.extent.minY)).composited(over:base)
    }

    private func makeVideoComposition(asset: AVAsset, includeText: Bool) -> AVVideoComposition? {
        let text = includeText ? overlayText : "", size = overlayTextSize, y = overlayTextY
        let needed = selectedFilter != .original || abs(brightness)>0.001 || abs(contrast-1)>0.001 || abs(saturation-1)>0.001 || enhanceAmount>0.001 || !text.isEmpty
        guard needed else { return nil }
        return AVVideoComposition(asset: asset) { [selectedFilter, brightness, contrast, saturation, enhanceAmount, text, size, y] request in
            var image = Self.applyLook(request.sourceImage, filter:selectedFilter, brightness:brightness, contrast:contrast, saturation:saturation, enhance:enhanceAmount)
            if !text.isEmpty { image = Self.addText(image, text:text, size:size, y:y) }; request.finish(with:image, context:nil)
        }
    }

    func exportProject() { startExport(clips, music: true) }
    func exportClip(_ id: UUID) { if let c = clips.first(where: {$0.id==id}) { startExport([c], music:false) } }
    private func startExport(_ source: [EditorClip], music: Bool) {
        player.pause(); isExporting = true; exportProgress = 0; exportedURL = nil
        Task { do {
            let (composition,mix)=try await buildComposition(source,includeMusic:music); let out=FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-\(UUID().uuidString).mp4"); let compatible=AVAssetExportSession.exportPresets(compatibleWith:composition); let preset=compatible.contains(exportQuality.presetName) ? exportQuality.presetName:AVAssetExportPresetHighestQuality
            guard let session=AVAssetExportSession(asset:composition,presetName:preset) else { throw NSError(domain:"VeloCut",code:2) }; session.outputURL=out; session.outputFileType=.mp4; session.audioMix=mix; session.videoComposition=makeVideoComposition(asset:composition,includeText:true); session.shouldOptimizeForNetworkUse=true
            exportTimer?.invalidate(); exportTimer=Timer.scheduledTimer(withTimeInterval:0.15,repeats:true){[weak self,weak session]_ in guard let self,let session else{return}; Task{@MainActor in self.exportProgress=Double(session.progress)}}
            await withCheckedContinuation { c in session.exportAsynchronously { c.resume() } }; guard session.status == .completed else { throw session.error ?? NSError(domain:"VeloCut",code:3) }; exportedURL=out; exportProgress=1
        } catch { errorMessage=error.localizedDescription }; exportTimer?.invalidate(); isExporting=false }
    }

    enum HapticKind { case light, medium, error, selection }
    func haptic(_ kind:HapticKind){ if kind == .selection { UISelectionFeedbackGenerator().selectionChanged() } else { UIImpactFeedbackGenerator(style: kind == .medium ? .medium : .light).impactOccurred() } }
}

struct PlayerView: UIViewControllerRepresentable {
    let player: AVPlayer
    func makeUIViewController(context: Context) -> AVPlayerViewController { let c=AVPlayerViewController(); c.player=player; c.showsPlaybackControls=false; c.videoGravity=.resizeAspect; return c }
    func updateUIViewController(_ uiViewController: AVPlayerViewController, context: Context) { uiViewController.player=player }
}

struct VideoPicker: UIViewControllerRepresentable {
    let onPick:([URL])->Void
    func makeCoordinator()->Coordinator{Coordinator(onPick)}
    func makeUIViewController(context:Context)->UIDocumentPickerViewController{let c=UIDocumentPickerViewController(forOpeningContentTypes:[.movie,.mpeg4Movie,.quickTimeMovie],asCopy:true);c.allowsMultipleSelection=true;c.delegate=context.coordinator;return c}
    func updateUIViewController(_ uiViewController:UIDocumentPickerViewController,context:Context){}
    final class Coordinator:NSObject,UIDocumentPickerDelegate{let cb:([URL])->Void;init(_ cb:@escaping([URL])->Void){self.cb=cb};func documentPicker(_ controller:UIDocumentPickerViewController,didPickDocumentsAt urls:[URL]){cb(urls)}}
}

struct AudioPicker: UIViewControllerRepresentable {
    let onPick:(URL)->Void
    func makeCoordinator()->Coordinator{Coordinator(onPick)}
    func makeUIViewController(context:Context)->UIDocumentPickerViewController{let c=UIDocumentPickerViewController(forOpeningContentTypes:[.audio],asCopy:true);c.delegate=context.coordinator;return c}
    func updateUIViewController(_ uiViewController:UIDocumentPickerViewController,context:Context){}
    final class Coordinator:NSObject,UIDocumentPickerDelegate{let cb:(URL)->Void;init(_ cb:@escaping(URL)->Void){self.cb=cb};func documentPicker(_ controller:UIDocumentPickerViewController,didPickDocumentsAt urls:[URL]){if let u=urls.first{cb(u)}}}
}

struct ShareSheet:UIViewControllerRepresentable{let url:URL;func makeUIViewController(context:Context)->UIActivityViewController{UIActivityViewController(activityItems:[url],applicationActivities:nil)};func updateUIViewController(_ uiViewController:UIActivityViewController,context:Context){}}

struct EditorView: View {
    @StateObject private var model=EditorViewModel()
    @State private var inspector:InspectorTool?
    @State private var curveTarget:CurveTarget?
    @State private var showShare=false
    @State private var photoItems:[PhotosPickerItem]=[]
    @State private var timelineDragStart:Double?
    @State private var contextClipID:UUID?
    @State private var clipDialog=false
    @State private var expandedLanes:Set<Int>=[]

    var body:some View{
        GeometryReader{root in
            ZStack{Color(uiColor:.systemGroupedBackground).ignoresSafeArea();VStack(spacing:0){topBar;preview.frame(height:min(350,max(220,root.size.height*0.37)));playback;if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{timeline.frame(maxHeight:.infinity)};bottomBar}.frame(width:root.size.width,height:root.size.height,alignment:.top)}
        }
        .sheet(isPresented:$model.isFileImporting){VideoPicker{model.isFileImporting=false;model.importVideos($0)}}
        .sheet(isPresented:$model.isAudioImporting){AudioPicker{model.isAudioImporting=false;model.importMusic($0)}}
        .sheet(item:$inspector){tool in InspectorSheet(tool:tool,model:model,curveTarget:$curveTarget).presentationDetents([.height(340),.medium,.large]).presentationDragIndicator(.visible)}
        .sheet(isPresented:$showShare){if let u=model.exportedURL{ShareSheet(url:u)}}
        .onChange(of:model.exportedURL){_,v in if v != nil{showShare=true}}
        .onChange(of:photoItems){_,items in loadPhotos(items)}
        .confirmationDialog("Действия клипа",isPresented:$clipDialog){if let id=contextClipID{Button("Дублировать"){model.duplicateClip(id)};Button("Дублировать как новое"){model.duplicateClipAsNew(id)};Button("Экспортировать кусок"){model.exportClip(id)};Button("Удалить",role:.destructive){model.deleteClip(id)}}}
        .alert("VeloCut",isPresented:Binding(get:{model.errorMessage != nil},set:{if !$0{model.errorMessage=nil}})){Button("OK",role:.cancel){}}message:{Text(model.errorMessage ?? "")}
        .overlay{if model.isExporting{exportOverlay}}
    }

    private var topBar:some View{HStack(spacing:10){VStack(alignment:.leading,spacing:1){Text("VeloCut").font(.headline);Text("\(model.clips.count) клип. • \(format(model.projectDuration))").font(.caption2).foregroundStyle(.secondary)};Spacer();PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos){Image(systemName:"photo.on.rectangle.angled").frame(width:34,height:34)};Button{model.isFileImporting=true}label:{Image(systemName:"folder").frame(width:34,height:34)};Button{inspector = .export}label:{Text("Экспорт").font(.subheadline.weight(.semibold)).padding(.horizontal,14).frame(height:36).background(Color.accentColor,in:Capsule()).foregroundStyle(.white)}.disabled(model.clips.isEmpty)}.padding(.horizontal,14).padding(.vertical,7).background(.ultraThinMaterial)}

    private var preview:some View{GeometryReader{g in ZStack{RoundedRectangle(cornerRadius:22).fill(.black);if !model.clips.isEmpty{PlayerView(player:model.player).clipShape(RoundedRectangle(cornerRadius:22));if !model.overlayText.isEmpty{Text(model.overlayText).font(.system(size:model.overlayTextSize,weight:.bold)).foregroundStyle(.white).shadow(radius:4).position(x:g.size.width/2,y:g.size.height*model.overlayTextY)}}else{VStack(spacing:14){Image(systemName:"film.stack").font(.system(size:42)).foregroundStyle(.white);Text("Добавить видео").foregroundStyle(.white);PhotosPicker(selection:$photoItems,maxSelectionCount:20,matching:.videos){Label("Из Фото",systemImage:"photo").padding(.horizontal,16).frame(height:38).background(.white,in:Capsule()).foregroundStyle(.black)}}};if model.isPreviewCaching{VStack{HStack{ProgressView().controlSize(.mini);Text("Кеш превью")}.font(.caption2).padding(7).background(.ultraThinMaterial,in:Capsule());Spacer()}.padding(10)}}}.padding(.horizontal,10).padding(.top,8)}

    private var playback:some View{HStack(spacing:12){Button{model.undo()}label:{Image(systemName:"arrow.uturn.backward")}.disabled(!model.canUndo);Button{model.redo()}label:{Image(systemName:"arrow.uturn.forward")}.disabled(!model.canRedo);Divider().frame(height:22);Button{model.seek(by:-10)}label:{Image(systemName:"gobackward.10")};Button{model.playPause()}label:{Image(systemName:model.isPlaying ? "pause.fill":"play.fill").font(.title3).frame(width:46,height:36).background(.thinMaterial,in:Capsule())};Button{model.seek(by:10)}label:{Image(systemName:"goforward.10")};Menu{Picker("Режим",selection:$model.playbackMode){ForEach(PlaybackMode.allCases){Label($0.rawValue,systemImage:$0.icon).tag($0)}};Toggle("Вернуть playhead",isOn:$model.returnPlayheadAfterStop)}label:{Image(systemName:model.playbackMode.icon).frame(width:34,height:34).background(.thinMaterial,in:Circle())};Spacer();Text("\(precise(model.projectTime)) / \(precise(model.projectDuration))").font(.caption.monospacedDigit()).foregroundStyle(.secondary)}.padding(.horizontal,14).padding(.vertical,8).disabled(model.clips.isEmpty)}

    private var timeline:some View{VStack(spacing:5){HStack{Label("Таймлайн",systemImage:"timeline.selection").font(.caption.weight(.semibold));Spacer();Menu{ForEach(SpeedCurvePreset.all.prefix(10)){p in Button(p.name){model.addSpeedFX(preset:p)}}}label:{Label("Speed FX",systemImage:"waveform.path.ecg.rectangle").font(.caption)};Button{model.timelineZoom=max(.55,model.timelineZoom-.2)}label:{Image(systemName:"minus.magnifyingglass")};Button{model.timelineZoom=min(3.2,model.timelineZoom+.2)}label:{Image(systemName:"plus.magnifyingglass")}}.padding(.horizontal,14).foregroundStyle(.secondary);GeometryReader{geo in timelineCanvas(geo)}.frame(minHeight:230)}.padding(.vertical,8).background(.regularMaterial).clipShape(RoundedRectangle(cornerRadius:22)).padding(.horizontal,8)}

    @ViewBuilder private func timelineCanvas(_ geo:GeometryProxy)->some View{
        let pps=34.0*model.timelineZoom, center=geo.size.width/2, rulerH=22.0, fxH=42.0, videoH=46.0, curveH=34.0
        let laneTop:(Int)->CGFloat={lane in var y=rulerH+fxH;for l in 0..<lane{y += videoH + (expandedLanes.contains(l) ? curveH:0)};return y}
        ZStack(alignment:.topLeading){RoundedRectangle(cornerRadius:18).fill(Color(uiColor:.secondarySystemGroupedBackground));TimelineRulerV4(projectTime:model.projectTime,duration:model.projectDuration,pps:pps).frame(height:rulerH)
            Rectangle().fill(Color.purple.opacity(.08)).frame(height:fxH-3).offset(y:rulerH);Text("FX").font(.system(size:9,weight:.bold)).padding(4).background(.thinMaterial,in:Capsule()).position(x:18,y:rulerH+12)
            ForEach(model.speedFX){fx in let w=max(48,fx.duration*pps),x=center+(fx.start-model.projectTime)*pps+w/2;SpeedFXBlock(fx:fx,width:w,onOpen:{curveTarget = .global(fx.id)},onMove:{model.moveSpeedFX(fx.id,delta:Double($0.width)/pps)},onDuplicate:{model.duplicateSpeedFX(fx.id)},onAtPlayhead:{model.duplicateSpeedFX(fx.id,atPlayhead:true)},onRepeat:{model.repeatSpeedFX(fx.id,count:4)},onDelete:{model.deleteSpeedFX(fx.id)}).position(x:x,y:rulerH+fxH/2)}
            ForEach(0..<3,id:\.self){lane in let top=laneTop(lane);RoundedRectangle(cornerRadius:8).fill(Color.secondary.opacity(.06)).frame(height:videoH-3).offset(y:top);Button{if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}}label:{HStack(spacing:3){Text("V\(lane+1)");Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down")}.font(.system(size:9,weight:.bold)).padding(4).background(.thinMaterial,in:Capsule())}.buttonStyle(.plain).position(x:24,y:top+12);if expandedLanes.contains(lane){RoundedRectangle(cornerRadius:7).fill(Color.accentColor.opacity(.035)).frame(height:curveH-2).offset(y:top+videoH);Text("Speed").font(.system(size:8,weight:.semibold)).foregroundStyle(.secondary).position(x:22,y:top+videoH+10)}}
            ForEach(Array(model.layouts.enumerated()),id:\.element.id){index,l in let w=max(52,l.duration*pps),x=center+(l.start-model.projectTime)*pps+w/2,top=laneTop(l.clip.track);TimelineClipCardV4(clip:l.clip,index:index,width:w,selected:l.id==model.selectedClipID,onTap:{model.selectClip(l.id)},onMenu:{model.selectedClipID=l.id;contextClipID=l.id;clipDialog=true},onMove:{model.moveClip(l.id,translation:$0,pps:pps)}).position(x:x,y:top+videoH/2);if expandedLanes.contains(l.clip.track){Button{model.selectedClipID=l.id;curveTarget = .clip(l.id)}label:{ZStack{RoundedRectangle(cornerRadius:6).fill(Color.accentColor.opacity(l.clip.curveEnabled ? .12:.04));CurveThumbnail(curve:l.clip.curveEnabled ? l.clip.speedCurve:.flat,lineWidth:1.5).padding(4)}}.buttonStyle(.plain).frame(width:w,height:curveH-5).position(x:x,y:top+videoH+curveH/2)}}
            Rectangle().fill(Color.accentColor).frame(width:2).position(x:center,y:geo.size.height/2).allowsHitTesting(false);Button{model.splitAtPlayhead()}label:{Image(systemName:"scissors").font(.system(size:11,weight:.bold)).foregroundStyle(.white).frame(width:29,height:29).background(Color.accentColor,in:Circle())}.position(x:center,y:rulerH+fxH+3)
        }.clipped().contentShape(Rectangle()).gesture(DragGesture(minimumDistance:12).onChanged{v in if timelineDragStart==nil{timelineDragStart=model.projectTime;model.beginScrub()};model.scrub(to:(timelineDragStart ?? model.projectTime)-Double(v.translation.width)/pps)}.onEnded{_ in timelineDragStart=nil;model.endScrub()})
    }

    private var bottomBar:some View{ScrollView(.horizontal,showsIndicators:false){HStack(spacing:5){tool("scissors","Обрезка",.trim);tool("speedometer","Скорость",.speed);tool("waveform","Аудио",.audio);tool("textformat","Текст",.text);tool("camera.filters","Фильтры",.filters);tool("slider.horizontal.3","Настройка",.adjust);tool("wand.and.stars","Улучшить",.enhance)}.padding(.horizontal,10)}.padding(.vertical,7).background(.ultraThinMaterial).disabled(model.clips.isEmpty)}
    private func tool(_ icon:String,_ title:String,_ t:InspectorTool)->some View{Button{inspector=t}label:{VStack(spacing:4){Image(systemName:icon).font(.system(size:17));Text(title).font(.caption2)}.frame(width:72,height:50)}.buttonStyle(.plain)}
    private var exportOverlay:some View{ZStack{Color.black.opacity(.3).ignoresSafeArea();VStack(spacing:12){ProgressView(value:model.exportProgress).frame(width:220);Text("Экспорт \(Int(model.exportProgress*100))%").font(.headline)}.padding(24).background(.ultraThickMaterial,in:RoundedRectangle(cornerRadius:22))}}
    private func loadPhotos(_ items:[PhotosPickerItem]){guard !items.isEmpty else{return};Task{var urls:[URL]=[];for item in items{if let m=try? await item.loadTransferable(type:PickedMovie.self){urls.append(m.url)}};await MainActor.run{model.importVideos(urls);photoItems=[]}}}
    private func format(_ s:Double)->String{let v=max(0,Int(s.rounded()));return String(format:"%d:%02d",v/60,v%60)}
    private func precise(_ s:Double)->String{let v=max(0,s),m=Int(v)/60;return String(format:"%d:%04.1f",m,v-Double(m*60))}
}

struct TimelineRulerV4:View{let projectTime:Double;let duration:Double;let pps:Double;var body:some View{Canvas{c,size in let half=Double(size.width/2)/pps,start=max(0,Int(floor(projectTime-half))-1),end=Int(ceil(projectTime+half))+1;if end>=start{for s in start...end{let x=size.width/2+CGFloat((Double(s)-projectTime)*pps);var p=Path();p.move(to:CGPoint(x:x,y:13));p.addLine(to:CGPoint(x:x,y:22));c.stroke(p,with:.color(.secondary.opacity(.35)),lineWidth:1);if s%2==0{let t=c.resolve(Text(String(format:"%d:%02d",s/60,s%60)).font(.system(size:8,design:.monospaced)).foregroundStyle(.secondary));c.draw(t,at:CGPoint(x:x+3,y:3),anchor:.topLeading)}}}}}}

struct TimelineClipCardV4:View{let clip:EditorClip;let index:Int;let width:Double;let selected:Bool;let onTap:()->Void;let onMenu:()->Void;let onMove:(CGSize)->Void;@State private var drag:CGSize=.zero;var body:some View{ZStack{RoundedRectangle(cornerRadius:8).fill(selected ? Color.accentColor.opacity(.24):Color.secondary.opacity(.14));VStack{HStack{Text("\(index+1)").font(.system(size:8,weight:.bold));Spacer();Text("\(clip.baseSpeed,specifier:"%g")×\(clip.curveEnabled ? " • curve":"")").font(.system(size:8))};Spacer();Text(clip.name).font(.system(size:8)).lineLimit(1)}.padding(5)}.frame(width:width,height:40).overlay(RoundedRectangle(cornerRadius:8).stroke(selected ? Color.accentColor:.clear,lineWidth:2)).offset(drag).onTapGesture{onTap()}.highPriorityGesture(LongPressGesture(minimumDuration:.32).sequenced(before:DragGesture(minimumDistance:0)).onChanged{v in if case .second(true,let d)=v,let d{drag=d.translation}}.onEnded{v in defer{drag=.zero};if case .second(true,let d)=v,let d{hypot(d.translation.width,d.translation.height)<10 ? onMenu():onMove(d.translation)}else{onMenu()}})}}

struct SpeedFXBlock:View{let fx:GlobalSpeedFX;let width:Double;let onOpen:()->Void;let onMove:(CGSize)->Void;let onDuplicate:()->Void;let onAtPlayhead:()->Void;let onRepeat:()->Void;let onDelete:()->Void;@State private var drag:CGSize=.zero;var body:some View{ZStack{RoundedRectangle(cornerRadius:7).fill(Color.purple.opacity(.18));CurveThumbnail(curve:fx.curve,lineWidth:1.4).padding(4);Text(fx.name).font(.system(size:8,weight:.semibold)).lineLimit(1).padding(4)}.frame(width:width,height:32).offset(drag).onTapGesture{onOpen()}.gesture(DragGesture(minimumDistance:8).onChanged{drag=$0.translation}.onEnded{onMove($0.translation);drag=.zero}).contextMenu{Button("Редактировать"){onOpen()};Button("Дублировать"){onDuplicate()};Button("Дублировать в playhead"){onAtPlayhead()};Button("Повторить ×4"){onRepeat()};Button("Удалить",role:.destructive){onDelete()}}}}

struct CurveEditorPanel:View{@ObservedObject var model:EditorViewModel;let target:CurveTarget;let onClose:()->Void;@State private var selectedPoint:UUID?;var body:some View{VStack(spacing:10){HStack{Button(action:onClose){Image(systemName:"chevron.down.circle.fill").font(.title2)};VStack(alignment:.leading){Text(title).font(.headline);Text("0.05× — 20× • перетаскивайте точки").font(.caption2).foregroundStyle(.secondary)};Spacer();Menu{ForEach(SpeedCurvePreset.all){p in Button(p.name){model.applyPreset(p,to:target)}}}label:{Label("Шаблон",systemImage:"sparkles").font(.caption)}}.padding(.horizontal,14);ScrollView(.horizontal,showsIndicators:false){HStack(spacing:8){ForEach(SpeedCurvePreset.all){p in Button{model.applyPreset(p,to:target)}label:{VStack(spacing:3){CurveThumbnail(curve:p.curve,lineWidth:1.5).frame(width:74,height:28);Text(p.name).font(.system(size:8))}.padding(6).background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))}.buttonStyle(.plain)}}.padding(.horizontal,12)};InteractiveCurveView(curve:model.curve(for:target),selectedPointID:selectedPoint,onSelect:{selectedPoint=$0},onMove:{id,t,s in model.moveCurvePoint(target,pointID:id,t:t,speed:s)},onAdd:{t,s in model.addCurvePoint(target,t:t,speed:s)}).frame(minHeight:150).padding(.horizontal,12);HStack{Button{model.addCurvePoint(target,t:model.normalizedPlayhead(for:target))}label:{Label("Точка",systemImage:"plus.circle")};Button{model.mirrorCurve(target)}label:{Label("Mirror",systemImage:"arrow.left.and.right")};if let id=selectedPoint{Button(role:.destructive){model.deleteCurvePoint(target,pointID:id);selectedPoint=nil}label:{Image(systemName:"trash")}};Spacer();Picker("",selection:Binding(get:{model.curve(for:target).interpolation},set:{model.setCurveInterpolation(target,$0)})){ForEach(CurveInterpolation.allCases){Text($0.rawValue).tag($0)}}.pickerStyle(.menu)}.font(.caption).padding(.horizontal,14);if case .global(let id)=target,let fx=model.speedFX.first(where:{$0.id==id}){VStack(spacing:8){HStack{Text("Strength");Slider(value:Binding(get:{fx.strength},set:{model.setSpeedFXStrength(id,$0)}),in:0...2);Text("\(fx.strength,specifier:"%.1f")×").monospacedDigit()};HStack{Text("Длина");Slider(value:Binding(get:{fx.duration},set:{model.setSpeedFXDuration(id,$0)}),in:.15...4);Text("\(fx.duration,specifier:"%.2f")с").monospacedDigit()};HStack{Picker("Режим",selection:Binding(get:{fx.mode},set:{model.setSpeedFXMode(id,$0)})){ForEach(SpeedFXMode.allCases){Text($0.rawValue).tag($0)}}.pickerStyle(.segmented);Button{model.duplicateSpeedFX(id)}label:{Image(systemName:"plus.square.on.square")};Button{model.repeatSpeedFX(id,count:4)}label:{Text("×4")}}}.font(.caption).padding(.horizontal,14)};Spacer(minLength:4)}.padding(.vertical,8).background(.regularMaterial)};private var title:String{switch target{case .clip:return "Speed Curve клипа";case .global:return "Global Speed FX"}}}

struct InspectorSheet:View{let tool:InspectorTool;@ObservedObject var model:EditorViewModel;@Binding var curveTarget:CurveTarget?;@Environment(\.dismiss)private var dismiss;@State private var speedTab=0;var body:some View{NavigationStack{Group{switch tool{case .trim:trim;case .speed:speed;case .audio:audio;case .text:text;case .filters:filters;case .adjust:adjust;case .enhance:enhance;case .export:export}}.padding(.horizontal,18).navigationTitle(title).navigationBarTitleDisplayMode(.inline).toolbar{ToolbarItem(placement:.confirmationAction){Button("Готово"){dismiss()}}}}};private var title:String{switch tool{case .trim:return"Обрезка";case .speed:return"Скорость";case .audio:return"Аудио";case .text:return"Текст";case .filters:return"Фильтры";case .adjust:return"Настройка";case .enhance:return"Улучшение";case .export:return"Экспорт"}}
    private var trim:some View{VStack(spacing:18){if let c=model.selectedClip{slider("Начало",Binding(get:{model.selectedClip?.trimStart ?? 0},set:{model.setTrimStart($0)}),0...c.duration);slider("Конец",Binding(get:{model.selectedClip?.trimEnd ?? c.duration},set:{model.setTrimEnd($0)}),0...c.duration);Text("Split — кнопка ножниц на playhead").font(.caption).foregroundStyle(.secondary)};Spacer()}.padding(.top)}
    private var speed:some View{VStack(spacing:14){Picker("",selection:$speedTab){Text("Обычная").tag(0);Text("Кривые").tag(1)}.pickerStyle(.segmented);if speedTab==0{Text("\(model.selectedClip?.baseSpeed ?? 1,specifier:"%.2f")×").font(.system(size:36,weight:.semibold,design:.rounded));Slider(value:Binding(get:{model.selectedClip?.baseSpeed ?? 1},set:{model.setBaseSpeed($0)}),in:.05...20);HStack{ForEach([0.25,0.5,1,2,5,10,20],id:\.self){v in Button("\(v,specifier:"%g")×"){model.setBaseSpeed(v)}.font(.caption).buttonStyle(.bordered)}}}else if let id=model.selectedClipID{Toggle("Кривая скорости",isOn:Binding(get:{model.selectedClip?.curveEnabled ?? false},set:{model.setCurveEnabled(id,$0)}));ScrollView(.horizontal,showsIndicators:false){HStack{ForEach(SpeedCurvePreset.all){p in Button{model.applyPreset(p,to:.clip(id))}label:{VStack{CurveThumbnail(curve:p.curve).frame(width:76,height:32);Text(p.name).font(.system(size:8))}.padding(6).background(.thinMaterial,in:RoundedRectangle(cornerRadius:10))}.buttonStyle(.plain)}}};Button{curveTarget = .clip(id);dismiss()}label:{Label("Открыть редактор кривой",systemImage:"arrow.up.left.and.arrow.down.right").frame(maxWidth:.infinity)}.buttonStyle(.borderedProminent);Menu{ForEach(SpeedCurvePreset.all.prefix(10)){p in Button(p.name){model.addSpeedFX(preset:p)}}}label:{Label("Добавить Global Speed FX",systemImage:"waveform.path.ecg.rectangle")}};Spacer()}.padding(.top,8)}
    private var audio:some View{VStack(spacing:18){slider("Громкость клипа",Binding(get:{model.selectedClip?.volume ?? 1},set:{model.setVolume($0)}),0...2);HStack{Text(model.musicName ?? "Музыка не добавлена").font(.caption);Spacer();Button("Добавить"){model.isAudioImporting=true}.buttonStyle(.bordered)};if model.musicURL != nil{slider("Музыка",$model.musicVolume,0...1.5)};Spacer()}.padding(.top)}
    private var text:some View{VStack(spacing:16){TextField("Текст",text:$model.overlayText).textFieldStyle(.roundedBorder);slider("Размер",$model.overlayTextSize,18...72);slider("Положение",$model.overlayTextY,.15...9);Spacer()}.padding(.top)}
    private var filters:some View{ScrollView(.horizontal,showsIndicators:false){HStack{ForEach(EditorFilter.allCases){f in Button{model.setFilter(f)}label:{VStack{RoundedRectangle(cornerRadius:14).fill(.thinMaterial).frame(width:82,height:82).overlay{Image(systemName:"camera.filters").font(.title)};Text(f.rawValue).font(.caption)}}.buttonStyle(.plain)}}.padding(.vertical,20)}}
    private var adjust:some View{VStack(spacing:18){slider("Яркость",Binding(get:{model.brightness},set:{model.updateColor(brightness:$0)}),-.35...35);slider("Контраст",Binding(get:{model.contrast},set:{model.updateColor(contrast:$0)}),.5...1.7);slider("Насыщенность",Binding(get:{model.saturation},set:{model.updateColor(saturation:$0)}),0...2);Spacer()}.padding(.top)}
    private var enhance:some View{VStack(spacing:18){Image(systemName:"wand.and.stars").font(.largeTitle);Text("Кеш обновляется после изменения, чтобы scrubbing оставался быстрым.").font(.caption).foregroundStyle(.secondary);slider("Интенсивность",Binding(get:{model.enhanceAmount},set:{model.setEnhance($0)}),0...1);Spacer()}.padding(.top)}
    private var export:some View{VStack(spacing:18){Picker("",selection:$model.exportQuality){ForEach(ExportQuality.allCases){Text($0.rawValue).tag($0)}}.pickerStyle(.segmented);LabeledContent("Клипы",value:"\(model.clips.count)");LabeledContent("Speed FX",value:"\(model.speedFX.count)");LabeledContent("Длительность",value:String(format:"%.1f сек",model.projectDuration));Button{dismiss();model.exportProject()}label:{Label("Экспортировать",systemImage:"square.and.arrow.up").frame(maxWidth:.infinity).frame(height:46)}.buttonStyle(.borderedProminent);Spacer()}.padding(.top)}
    private func slider(_ title:String,_ value:Binding<Double>,_ range:ClosedRange<Double>)->some View{VStack(alignment:.leading,spacing:6){Text(title).font(.caption);Slider(value:value,in:range)}}
}

@main struct VeloCutAIApp:App{var body:some Scene{WindowGroup{EditorView().tint(.blue)}}}
