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
    var systemImage: String {
        switch self {
        case .original: return "circle.lefthalf.filled"
        case .vivid: return "sun.max.fill"
        case .mono: return "circle.righthalf.filled"
        case .cinematic: return "film.fill"
        case .warm: return "thermometer.sun.fill"
        case .cool: return "snowflake"
        }
    }
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

enum InspectorTool: String, Identifiable {
    case trim, speed, audio, text, filters, adjust, enhance, export
    var id: String { rawValue }
}

enum PlaybackMode: String, CaseIterable, Identifiable {
    case project = "Проект"
    case clip = "Клип"
    case loopClip = "Цикл клипа"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .project: return "play.rectangle.on.rectangle"
        case .clip: return "play.square"
        case .loopClip: return "repeat.1"
        }
    }
}

struct PickedMovie: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let destination = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-Photo-\(UUID().uuidString).\(ext)")
            try? FileManager.default.removeItem(at: destination)
            try FileManager.default.copyItem(at: received.file, to: destination)
            return PickedMovie(url: destination)
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
    var speed: Double
    var volume: Double
    var track: Int

    init(id: UUID = UUID(), url: URL, name: String, duration: Double, trimStart: Double, trimEnd: Double, speed: Double = 1, volume: Double = 1, track: Int = 0) {
        self.id = id
        self.url = url
        self.name = name
        self.duration = duration
        self.trimStart = trimStart
        self.trimEnd = trimEnd
        self.speed = speed
        self.volume = volume
        self.track = track
    }

    var sourceDuration: Double { max(0.05, trimEnd - trimStart) }
    var outputDuration: Double { sourceDuration / max(0.1, speed) }
}

private struct ProjectSnapshot {
    var clips: [EditorClip]
    var selectedClipID: UUID?
    var overlayText: String
    var overlayTextSize: Double
    var overlayTextY: Double
    var selectedFilter: EditorFilter
    var brightness: Double
    var contrast: Double
    var saturation: Double
    var enhanceAmount: Double
}

@MainActor
final class EditorViewModel: ObservableObject {
    @Published var clips: [EditorClip] = []
    @Published var selectedClipID: UUID?
    @Published var player = AVPlayer()
    @Published var projectTime: Double = 0
    @Published var isPlaying = false
    @Published var isFileImporting = false
    @Published var isAudioImporting = false
    @Published var isExporting = false
    @Published var exportProgress: Double = 0
    @Published var exportedURL: URL?
    @Published var errorMessage: String?
    @Published var selectedFilter: EditorFilter = .original
    @Published var brightness: Double = 0
    @Published var contrast: Double = 1
    @Published var saturation: Double = 1
    @Published var enhanceAmount: Double = 0
    @Published var overlayText: String = ""
    @Published var overlayTextSize: Double = 36
    @Published var overlayTextY: Double = 0.82
    @Published var musicURL: URL?
    @Published var musicName: String?
    @Published var musicVolume: Double = 0.8
    @Published var exportQuality: ExportQuality = .fullHD
    @Published var timelineZoom: Double = 1
    @Published var playbackMode: PlaybackMode = .project
    @Published var returnPlayheadAfterStop = true
    @Published var isPreviewCaching = false
    @Published var cacheRevision: Int = 0

    private var timeObserver: Any?
    private var undoStack: [ProjectSnapshot] = []
    private var redoStack: [ProjectSnapshot] = []
    private var progressTimer: Timer?
    private var previewRebuildTask: Task<Void, Never>?
    private var assetCache: [URL: AVURLAsset] = [:]
    private var playbackStartTime: Double = 0
    private var playbackClipID: UUID?
    private var isScrubbing = false

    init() {
        player.automaticallyWaitsToMinimizeStalling = false
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.033, preferredTimescale: 600), queue: .main) { [weak self] time in
            guard let self else { return }
            Task { @MainActor in
                guard !self.isScrubbing else { return }
                self.projectTime = min(max(0, CMTimeGetSeconds(time)), max(0, self.projectDuration))
                self.isPlaying = self.player.rate != 0
                self.enforcePlaybackBoundary()
                if self.playbackMode == .project || !self.isPlaying {
                    self.syncSelectionForProjectTime()
                }
            }
        }
    }

    var selectedClip: EditorClip? { clips.first(where: { $0.id == selectedClipID }) }
    var selectedIndex: Int? {
        guard let selectedClipID else { return nil }
        return clips.firstIndex(where: { $0.id == selectedClipID })
    }
    var projectDuration: Double { clips.reduce(0) { $0 + $1.outputDuration } }
    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }

    func asset(for url: URL) -> AVURLAsset {
        if let cached = assetCache[url] { return cached }
        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: true])
        assetCache[url] = asset
        return asset
    }

    func importVideos(_ urls: [URL]) {
        guard !urls.isEmpty else { return }
        Task {
            var imported: [EditorClip] = []
            for url in urls {
                do {
                    let a = asset(for: url)
                    let time = try await a.load(.duration)
                    let duration = max(0.1, CMTimeGetSeconds(time))
                    imported.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: duration, trimStart: 0, trimEnd: duration))
                } catch {
                    errorMessage = "Не удалось открыть \(url.lastPathComponent): \(error.localizedDescription)"
                }
            }
            guard !imported.isEmpty else { return }
            registerUndo()
            clips.append(contentsOf: imported)
            if selectedClipID == nil { selectedClipID = imported.first?.id }
            schedulePreviewRebuild(immediate: true, seekTo: projectTime)
        }
    }

    func importMusic(_ url: URL) {
        musicURL = url
        musicName = url.deletingPathExtension().lastPathComponent
        schedulePreviewRebuild()
    }

    func projectStart(of id: UUID) -> Double {
        var cursor = 0.0
        for clip in clips {
            if clip.id == id { return cursor }
            cursor += clip.outputDuration
        }
        return 0
    }

    func projectBounds(of id: UUID) -> ClosedRange<Double>? {
        guard let clip = clips.first(where: { $0.id == id }) else { return nil }
        let start = projectStart(of: id)
        return start...(start + clip.outputDuration)
    }

    private func clipAtProjectTime(_ time: Double) -> (index: Int, start: Double, end: Double)? {
        guard !clips.isEmpty else { return nil }
        var cursor = 0.0
        for (index, clip) in clips.enumerated() {
            let end = cursor + clip.outputDuration
            if time < end || index == clips.count - 1 { return (index, cursor, end) }
            cursor = end
        }
        return nil
    }

    func selectClip(_ id: UUID, seekToStart: Bool = true) {
        selectedClipID = id
        if seekToStart {
            seekProject(to: projectStart(of: id), exact: true)
        }
    }

    func syncSelectionForProjectTime() {
        guard let info = clipAtProjectTime(projectTime) else { return }
        let id = clips[info.index].id
        if selectedClipID != id { selectedClipID = id }
    }

    func beginScrub() {
        isScrubbing = true
        if player.rate != 0 { player.pause() }
        isPlaying = false
    }

    func scrub(to time: Double) {
        let target = min(max(0, time), max(0, projectDuration))
        projectTime = target
        syncSelectionForProjectTime()
        seekProject(to: target, exact: true)
    }

    func endScrub() {
        isScrubbing = false
        seekProject(to: projectTime, exact: true)
    }

    func seekProject(to time: Double, exact: Bool = false) {
        let target = min(max(0, time), max(0, projectDuration))
        projectTime = target
        let cm = CMTime(seconds: target, preferredTimescale: 600)
        if exact {
            player.seek(to: cm, toleranceBefore: .zero, toleranceAfter: .zero)
        } else {
            player.seek(to: cm, toleranceBefore: CMTime(seconds: 0.03, preferredTimescale: 600), toleranceAfter: CMTime(seconds: 0.03, preferredTimescale: 600))
        }
    }

    func seek(by delta: Double) {
        beginScrub()
        scrub(to: projectTime + delta)
        endScrub()
    }

    func playPause() {
        guard !clips.isEmpty else { return }
        if player.rate != 0 {
            stopPlayback(manual: true)
            return
        }

        playbackStartTime = projectTime
        playbackClipID = selectedClipID ?? clipAtProjectTime(projectTime).map { clips[$0.index].id }

        switch playbackMode {
        case .project:
            if projectTime >= projectDuration - 0.03 { seekProject(to: 0, exact: true); playbackStartTime = 0 }
        case .clip, .loopClip:
            if let id = playbackClipID, let bounds = projectBounds(of: id), (projectTime < bounds.lowerBound || projectTime >= bounds.upperBound - 0.03) {
                seekProject(to: bounds.lowerBound, exact: true)
                playbackStartTime = bounds.lowerBound
            }
        }
        player.play()
        isPlaying = true
    }

    private func stopPlayback(manual: Bool) {
        player.pause()
        isPlaying = false
        if returnPlayheadAfterStop && (manual || playbackMode != .loopClip) {
            seekProject(to: playbackStartTime, exact: true)
            syncSelectionForProjectTime()
        }
    }

    private func enforcePlaybackBoundary() {
        guard player.rate != 0 else { return }
        switch playbackMode {
        case .project:
            if projectTime >= projectDuration - 0.02 {
                player.pause()
                isPlaying = false
                if returnPlayheadAfterStop { seekProject(to: playbackStartTime, exact: true) }
            }
        case .clip:
            guard let id = playbackClipID, let bounds = projectBounds(of: id) else { return }
            if projectTime >= bounds.upperBound - 0.02 {
                player.pause()
                isPlaying = false
                if returnPlayheadAfterStop { seekProject(to: playbackStartTime, exact: true) }
                else { seekProject(to: bounds.upperBound, exact: true) }
            }
        case .loopClip:
            guard let id = playbackClipID, let bounds = projectBounds(of: id) else { return }
            if projectTime >= bounds.upperBound - 0.02 {
                seekProject(to: bounds.lowerBound, exact: true)
                player.play()
                isPlaying = true
            }
        }
    }

    func splitAtPlayhead() {
        guard let info = clipAtProjectTime(projectTime) else { return }
        let clip = clips[info.index]
        let offsetOutput = projectTime - info.start
        let splitSource = clip.trimStart + offsetOutput * clip.speed
        guard splitSource > clip.trimStart + 0.08, splitSource < clip.trimEnd - 0.08 else {
            haptic(.error)
            return
        }
        registerUndo()
        var left = clip
        left.trimEnd = splitSource
        let right = EditorClip(url: clip.url, name: clip.name, duration: clip.duration, trimStart: splitSource, trimEnd: clip.trimEnd, speed: clip.speed, volume: clip.volume, track: clip.track)
        clips[info.index] = left
        clips.insert(right, at: info.index + 1)
        selectedClipID = right.id
        schedulePreviewRebuild(immediate: true, seekTo: projectTime)
        haptic(.medium)
    }

    func duplicateClip(_ id: UUID) {
        guard let index = clips.firstIndex(where: { $0.id == id }) else { return }
        let clip = clips[index]
        registerUndo()
        let copy = EditorClip(url: clip.url, name: clip.name + " copy", duration: clip.duration, trimStart: clip.trimStart, trimEnd: clip.trimEnd, speed: clip.speed, volume: clip.volume, track: clip.track)
        clips.insert(copy, at: index + 1)
        selectedClipID = copy.id
        schedulePreviewRebuild(immediate: true, seekTo: projectStart(of: copy.id))
        haptic(.light)
    }

    func duplicateClipAsNew(_ id: UUID) {
        guard let index = clips.firstIndex(where: { $0.id == id }) else { return }
        let clip = clips[index]
        Task {
            do {
                let ext = clip.url.pathExtension.isEmpty ? "mov" : clip.url.pathExtension
                let newURL = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-New-\(UUID().uuidString).\(ext)")
                try? FileManager.default.removeItem(at: newURL)
                try FileManager.default.copyItem(at: clip.url, to: newURL)
                registerUndo()
                let copy = EditorClip(url: newURL, name: clip.name + " new", duration: clip.duration, trimStart: clip.trimStart, trimEnd: clip.trimEnd, speed: clip.speed, volume: clip.volume, track: clip.track)
                clips.insert(copy, at: min(index + 1, clips.count))
                selectedClipID = copy.id
                schedulePreviewRebuild(immediate: true, seekTo: projectStart(of: copy.id))
                haptic(.success)
            } catch {
                errorMessage = "Не удалось создать независимую копию: \(error.localizedDescription)"
            }
        }
    }

    func deleteClip(_ id: UUID) {
        guard let index = clips.firstIndex(where: { $0.id == id }) else { return }
        registerUndo()
        clips.remove(at: index)
        selectedClipID = clips.isEmpty ? nil : clips[min(index, clips.count - 1)].id
        projectTime = min(projectTime, projectDuration)
        schedulePreviewRebuild(immediate: true, seekTo: projectTime)
        haptic(.rigid)
    }

    func moveClip(_ id: UUID, translation: CGSize, pointsPerSecond: Double) {
        guard let originalIndex = clips.firstIndex(where: { $0.id == id }) else { return }
        let clip = clips[originalIndex]
        let horizontalUnit = max(72, min(180, clip.outputDuration * pointsPerSecond * 0.7))
        let horizontalSteps = Int((translation.width / horizontalUnit).rounded())
        let verticalSteps = Int((translation.height / 52).rounded())
        guard horizontalSteps != 0 || verticalSteps != 0 else { return }
        registerUndo()

        var moved = clips[originalIndex]
        moved.track = min(2, max(0, moved.track + verticalSteps))
        clips.remove(at: originalIndex)
        let destination = min(clips.count, max(0, originalIndex + horizontalSteps))
        clips.insert(moved, at: destination)
        selectedClipID = moved.id
        schedulePreviewRebuild(immediate: true, seekTo: projectStart(of: moved.id))
        haptic(.medium)
    }

    private func mutateSelectedClip(register: Bool = true, _ change: (inout EditorClip) -> Void) {
        guard let index = selectedIndex else { return }
        if register { registerUndo() }
        change(&clips[index])
        schedulePreviewRebuild(seekTo: projectTime)
    }

    func setTrimStart(_ value: Double) {
        guard let clip = selectedClip else { return }
        let oldStart = projectStart(of: clip.id)
        mutateSelectedClip { $0.trimStart = min(max(0, value), max(0, $0.trimEnd - 0.05)) }
        schedulePreviewRebuild(seekTo: oldStart)
    }

    func setTrimEnd(_ value: Double) {
        mutateSelectedClip { $0.trimEnd = max(min($0.duration, value), min($0.duration, $0.trimStart + 0.05)) }
    }

    func setSpeed(_ value: Double) {
        registerUndo()
        mutateSelectedClip(register: false) { $0.speed = min(max(value, 0.1), 5) }
    }

    func setVolume(_ value: Double) {
        mutateSelectedClip { $0.volume = min(max(value, 0), 2) }
    }

    func setFilter(_ filter: EditorFilter) {
        registerUndo()
        selectedFilter = filter
        schedulePreviewRebuild(seekTo: projectTime)
    }

    func updateColor(brightness: Double? = nil, contrast: Double? = nil, saturation: Double? = nil) {
        if let brightness { self.brightness = brightness }
        if let contrast { self.contrast = contrast }
        if let saturation { self.saturation = saturation }
        schedulePreviewRebuild(seekTo: projectTime)
    }

    func resetColor() {
        registerUndo()
        brightness = 0
        contrast = 1
        saturation = 1
        enhanceAmount = 0
        schedulePreviewRebuild(seekTo: projectTime)
    }

    func setEnhance(_ value: Double) {
        enhanceAmount = value
        schedulePreviewRebuild(seekTo: projectTime)
    }

    func registerUndo() {
        undoStack.append(snapshot())
        if undoStack.count > 40 { undoStack.removeFirst() }
        redoStack.removeAll()
        objectWillChange.send()
    }

    func undo() {
        guard let previous = undoStack.popLast() else { return }
        redoStack.append(snapshot())
        restore(previous)
        haptic(.selection)
    }

    func redo() {
        guard let next = redoStack.popLast() else { return }
        undoStack.append(snapshot())
        restore(next)
        haptic(.selection)
    }

    private func snapshot() -> ProjectSnapshot {
        ProjectSnapshot(clips: clips, selectedClipID: selectedClipID, overlayText: overlayText, overlayTextSize: overlayTextSize, overlayTextY: overlayTextY, selectedFilter: selectedFilter, brightness: brightness, contrast: contrast, saturation: saturation, enhanceAmount: enhanceAmount)
    }

    private func restore(_ snapshot: ProjectSnapshot) {
        clips = snapshot.clips
        selectedClipID = snapshot.selectedClipID
        overlayText = snapshot.overlayText
        overlayTextSize = snapshot.overlayTextSize
        overlayTextY = snapshot.overlayTextY
        selectedFilter = snapshot.selectedFilter
        brightness = snapshot.brightness
        contrast = snapshot.contrast
        saturation = snapshot.saturation
        enhanceAmount = snapshot.enhanceAmount
        projectTime = min(projectTime, projectDuration)
        schedulePreviewRebuild(immediate: true, seekTo: projectTime)
        objectWillChange.send()
    }

    func schedulePreviewRebuild(immediate: Bool = false, seekTo target: Double? = nil) {
        previewRebuildTask?.cancel()
        isPreviewCaching = true
        let preserve = min(max(0, target ?? projectTime), max(0, projectDuration))
        previewRebuildTask = Task { [weak self] in
            if !immediate { try? await Task.sleep(nanoseconds: 120_000_000) }
            guard !Task.isCancelled, let self else { return }
            await self.rebuildPreviewCache(seekTo: preserve)
        }
    }

    private func rebuildPreviewCache(seekTo target: Double) async {
        guard !clips.isEmpty else {
            player.pause()
            player.replaceCurrentItem(with: nil)
            isPreviewCaching = false
            return
        }
        do {
            let (composition, audioMix) = try await buildComposition(from: clips, includeMusic: true)
            if Task.isCancelled { return }
            let wasPlaying = player.rate != 0
            let item = AVPlayerItem(asset: composition)
            item.preferredForwardBufferDuration = 1.5
            item.audioMix = audioMix
            item.videoComposition = makeFilterComposition(for: composition, includeText: false)
            player.replaceCurrentItem(with: item)
            let safe = min(max(0, target), max(0, projectDuration))
            projectTime = safe
            await player.seek(to: CMTime(seconds: safe, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            if wasPlaying { player.play() }
            cacheRevision += 1
            isPreviewCaching = false
            syncSelectionForProjectTime()
        } catch {
            isPreviewCaching = false
            errorMessage = "Ошибка кеша предпросмотра: \(error.localizedDescription)"
        }
    }

    private func buildComposition(from sourceClips: [EditorClip], includeMusic: Bool) async throws -> (AVMutableComposition, AVMutableAudioMix) {
        let composition = AVMutableComposition()
        guard let videoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw NSError(domain: "VeloCut", code: 20, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать видеодорожку"])
        }
        let audioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        let clipAudioParams = audioTrack.map { AVMutableAudioMixInputParameters(track: $0) }
        var cursor = CMTime.zero
        var firstTransform: CGAffineTransform?

        for clip in sourceClips {
            let sourceAsset = asset(for: clip.url)
            guard let sourceVideo = try await sourceAsset.loadTracks(withMediaType: .video).first else { continue }
            if firstTransform == nil { firstTransform = try await sourceVideo.load(.preferredTransform) }
            let sourceDuration = max(0.05, clip.trimEnd - clip.trimStart)
            let sourceRange = CMTimeRange(start: CMTime(seconds: clip.trimStart, preferredTimescale: 600), duration: CMTime(seconds: sourceDuration, preferredTimescale: 600))
            try videoTrack.insertTimeRange(sourceRange, of: sourceVideo, at: cursor)
            if let sourceAudio = try await sourceAsset.loadTracks(withMediaType: .audio).first, let audioTrack {
                try? audioTrack.insertTimeRange(sourceRange, of: sourceAudio, at: cursor)
            }
            let insertedRange = CMTimeRange(start: cursor, duration: CMTime(seconds: sourceDuration, preferredTimescale: 600))
            let outputDuration = CMTime(seconds: clip.outputDuration, preferredTimescale: 600)
            videoTrack.scaleTimeRange(insertedRange, toDuration: outputDuration)
            if let audioTrack { audioTrack.scaleTimeRange(insertedRange, toDuration: outputDuration) }
            clipAudioParams?.setVolume(Float(clip.volume), at: cursor)
            cursor = cursor + outputDuration
        }

        if let firstTransform { videoTrack.preferredTransform = firstTransform }

        var musicParams: AVMutableAudioMixInputParameters?
        if includeMusic, let musicURL, let musicTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
            let musicAsset = asset(for: musicURL)
            if let sourceMusic = try await musicAsset.loadTracks(withMediaType: .audio).first {
                let musicDuration = try await musicAsset.load(.duration)
                let available = min(CMTimeGetSeconds(musicDuration), CMTimeGetSeconds(cursor))
                if available > 0.05 {
                    let range = CMTimeRange(start: .zero, duration: CMTime(seconds: available, preferredTimescale: 600))
                    try? musicTrack.insertTimeRange(range, of: sourceMusic, at: .zero)
                    let p = AVMutableAudioMixInputParameters(track: musicTrack)
                    p.setVolume(Float(musicVolume), at: .zero)
                    musicParams = p
                }
            }
        }

        let audioMix = AVMutableAudioMix()
        audioMix.inputParameters = [clipAudioParams, musicParams].compactMap { $0 }
        return (composition, audioMix)
    }

    private func makeFilterComposition(for asset: AVAsset, includeText: Bool) -> AVVideoComposition? {
        let text = includeText ? overlayText : ""
        let textSize = overlayTextSize
        let textY = overlayTextY
        let needed = selectedFilter != .original || abs(brightness) > 0.001 || abs(contrast - 1) > 0.001 || abs(saturation - 1) > 0.001 || enhanceAmount > 0.001 || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        guard needed else { return nil }
        return AVVideoComposition(asset: asset) { [selectedFilter, brightness, contrast, saturation, enhanceAmount, text, textSize, textY] request in
            var image = Self.applyLook(to: request.sourceImage, filter: selectedFilter, brightness: brightness, contrast: contrast, saturation: saturation, enhanceAmount: enhanceAmount)
            if !text.isEmpty { image = Self.applyTextOverlay(to: image, text: text, fontSize: textSize, verticalPosition: textY) }
            request.finish(with: image, context: nil)
        }
    }

    nonisolated private static func applyLook(to source: CIImage, filter: EditorFilter, brightness: Double, contrast: Double, saturation: Double, enhanceAmount: Double) -> CIImage {
        let extent = source.extent
        var image = source.clampedToExtent()
        switch filter {
        case .original: break
        case .vivid:
            image = image.applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 1.28, kCIInputContrastKey: 1.08])
            image = image.applyingFilter("CIVibrance", parameters: ["inputAmount": 0.35])
        case .mono:
            image = image.applyingFilter("CIPhotoEffectNoir")
        case .cinematic:
            image = image.applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0.82, kCIInputContrastKey: 1.16])
            image = image.applyingFilter("CITemperatureAndTint", parameters: ["inputNeutral": CIVector(x: 6500, y: 0), "inputTargetNeutral": CIVector(x: 5800, y: 0)])
        case .warm:
            image = image.applyingFilter("CITemperatureAndTint", parameters: ["inputNeutral": CIVector(x: 6500, y: 0), "inputTargetNeutral": CIVector(x: 5000, y: 0)])
        case .cool:
            image = image.applyingFilter("CITemperatureAndTint", parameters: ["inputNeutral": CIVector(x: 6500, y: 0), "inputTargetNeutral": CIVector(x: 8000, y: 0)])
        }
        image = image.applyingFilter("CIColorControls", parameters: [kCIInputBrightnessKey: brightness, kCIInputContrastKey: contrast, kCIInputSaturationKey: saturation])
        if enhanceAmount > 0.001 {
            image = image.applyingFilter("CINoiseReduction", parameters: ["inputNoiseLevel": min(0.07, 0.015 + enhanceAmount * 0.045), "inputSharpness": 0.4 + enhanceAmount * 0.4])
            image = image.applyingFilter("CISharpenLuminance", parameters: [kCIInputSharpnessKey: enhanceAmount * 0.75])
            image = image.applyingFilter("CIVibrance", parameters: ["inputAmount": enhanceAmount * 0.18])
        }
        return image.cropped(to: extent)
    }

    nonisolated private static func applyTextOverlay(to base: CIImage, text: String, fontSize: Double, verticalPosition: Double) -> CIImage {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let generator = CIFilter(name: "CITextImageGenerator") else { return base }
        let scaledFont = fontSize * max(1, base.extent.width / 1080)
        generator.setValue(text, forKey: "inputText")
        generator.setValue("HelveticaNeue-Bold", forKey: "inputFontName")
        generator.setValue(scaledFont, forKey: "inputFontSize")
        generator.setValue(1.0, forKey: "inputScaleFactor")
        guard var textImage = generator.outputImage else { return base }
        let maxWidth = base.extent.width * 0.88
        if textImage.extent.width > maxWidth {
            let scale = maxWidth / textImage.extent.width
            textImage = textImage.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        }
        let x = base.extent.midX - textImage.extent.width / 2 - textImage.extent.minX
        let desiredY = max(0, min(base.extent.height - textImage.extent.height, base.extent.height * CGFloat(1 - verticalPosition) - textImage.extent.height / 2))
        let translated = textImage.transformed(by: CGAffineTransform(translationX: x, y: desiredY - textImage.extent.minY))
        return translated.composited(over: base)
    }

    func exportProject() {
        guard !clips.isEmpty else { return }
        player.pause()
        isExporting = true
        exportProgress = 0
        exportedURL = nil
        Task {
            do {
                exportedURL = try await makeExport(sourceClips: clips, includeMusic: true)
                exportProgress = 1
                haptic(.success)
            } catch {
                errorMessage = error.localizedDescription
                haptic(.error)
            }
            progressTimer?.invalidate()
            progressTimer = nil
            isExporting = false
        }
    }

    func exportClip(_ id: UUID) {
        guard let clip = clips.first(where: { $0.id == id }) else { return }
        player.pause()
        isExporting = true
        exportProgress = 0
        exportedURL = nil
        Task {
            do {
                exportedURL = try await makeExport(sourceClips: [clip], includeMusic: false)
                exportProgress = 1
                haptic(.success)
            } catch {
                errorMessage = error.localizedDescription
                haptic(.error)
            }
            progressTimer?.invalidate()
            progressTimer = nil
            isExporting = false
        }
    }

    private func makeExport(sourceClips: [EditorClip], includeMusic: Bool) async throws -> URL {
        let (composition, audioMix) = try await buildComposition(from: sourceClips, includeMusic: includeMusic)
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-\(UUID().uuidString).mp4")
        let compatible = AVAssetExportSession.exportPresets(compatibleWith: composition)
        let preset = compatible.contains(exportQuality.presetName) ? exportQuality.presetName : AVAssetExportPresetHighestQuality
        guard let session = AVAssetExportSession(asset: composition, presetName: preset) else {
            throw NSError(domain: "VeloCut", code: 11, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать экспорт"])
        }
        session.outputURL = output
        session.outputFileType = .mp4
        session.shouldOptimizeForNetworkUse = true
        session.audioMix = audioMix
        session.videoComposition = makeFilterComposition(for: composition, includeText: true)
        progressTimer?.invalidate()
        progressTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self, weak session] _ in
            guard let self, let session else { return }
            Task { @MainActor in self.exportProgress = Double(session.progress) }
        }
        await withCheckedContinuation { continuation in
            session.exportAsynchronously { continuation.resume() }
        }
        guard session.status == .completed else {
            throw session.error ?? NSError(domain: "VeloCut", code: 12, userInfo: [NSLocalizedDescriptionKey: "Ошибка экспорта"])
        }
        return output
    }

    enum HapticKind { case light, medium, rigid, selection, success, error }
    func haptic(_ kind: HapticKind) {
        switch kind {
        case .light: UIImpactFeedbackGenerator(style: .light).impactOccurred()
        case .medium: UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        case .rigid: UIImpactFeedbackGenerator(style: .rigid).impactOccurred()
        case .selection: UISelectionFeedbackGenerator().selectionChanged()
        case .success: UINotificationFeedbackGenerator().notificationOccurred(.success)
        case .error: UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }
}

struct PlayerView: UIViewControllerRepresentable {
    let player: AVPlayer
    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let controller = AVPlayerViewController()
        controller.player = player
        controller.showsPlaybackControls = false
        controller.videoGravity = .resizeAspect
        return controller
    }
    func updateUIViewController(_ uiViewController: AVPlayerViewController, context: Context) {
        uiViewController.player = player
    }
}

struct VideoPicker: UIViewControllerRepresentable {
    let onPick: ([URL]) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(onPick) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let controller = UIDocumentPickerViewController(forOpeningContentTypes: [.movie, .mpeg4Movie, .quickTimeMovie], asCopy: true)
        controller.allowsMultipleSelection = true
        controller.delegate = context.coordinator
        return controller
    }
    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}
    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: ([URL]) -> Void
        init(_ onPick: @escaping ([URL]) -> Void) { self.onPick = onPick }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) { onPick(urls) }
    }
}

struct AudioPicker: UIViewControllerRepresentable {
    let onPick: (URL) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(onPick) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let controller = UIDocumentPickerViewController(forOpeningContentTypes: [.audio], asCopy: true)
        controller.delegate = context.coordinator
        return controller
    }
    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}
    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: (URL) -> Void
        init(_ onPick: @escaping (URL) -> Void) { self.onPick = onPick }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) { if let url = urls.first { onPick(url) } }
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct EditorView: View {
    @StateObject private var model = EditorViewModel()
    @State private var inspector: InspectorTool?
    @State private var showShare = false
    @State private var showProjectInfo = false
    @State private var photoItems: [PhotosPickerItem] = []
    @State private var timelineDragStart: Double?
    @State private var clipActionPresented = false
    @State private var contextClipID: UUID?

    var body: some View {
        GeometryReader { root in
            ZStack {
                Color(uiColor: .systemGroupedBackground).ignoresSafeArea()
                VStack(spacing: 0) {
                    topBar
                    previewArea
                        .frame(height: min(360, max(230, root.size.height * 0.39)))
                    playbackBar
                    timelineArea
                        .frame(maxHeight: .infinity)
                    bottomToolBar
                }
                .frame(width: root.size.width, height: root.size.height, alignment: .top)
            }
        }
        .sheet(isPresented: $model.isFileImporting) {
            VideoPicker { urls in model.isFileImporting = false; model.importVideos(urls) }
        }
        .sheet(isPresented: $model.isAudioImporting) {
            AudioPicker { url in model.isAudioImporting = false; model.importMusic(url) }
        }
        .sheet(item: $inspector) { tool in
            InspectorSheet(tool: tool, model: model)
                .presentationDetents([.height(300), .medium, .large])
                .presentationDragIndicator(.visible)
                .presentationBackground(.ultraThinMaterial)
        }
        .sheet(isPresented: $showShare) {
            if let url = model.exportedURL { ShareSheet(url: url) }
        }
        .sheet(isPresented: $showProjectInfo) {
            ProjectInfoSheet(model: model).presentationDetents([.medium]).presentationDragIndicator(.visible)
        }
        .onChange(of: model.exportedURL) { _, value in if value != nil { showShare = true } }
        .onChange(of: photoItems) { _, items in loadPhotoItems(items) }
        .confirmationDialog("Действия клипа", isPresented: $clipActionPresented, titleVisibility: .visible) {
            if let id = contextClipID {
                Button("Дублировать") { model.duplicateClip(id) }
                Button("Дублировать как новое") { model.duplicateClipAsNew(id) }
                Button("Экспортировать этот кусок") { model.exportClip(id) }
                Button("Удалить", role: .destructive) { model.deleteClip(id) }
            }
            Button("Отмена", role: .cancel) {}
        }
        .alert("VeloCut", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
            Button("OK", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
        .overlay { if model.isExporting { exportOverlay } }
    }

    private var topBar: some View {
        HStack(spacing: 10) {
            Button { showProjectInfo = true } label: {
                Image(systemName: "chevron.down")
                    .font(.headline.weight(.semibold))
                    .frame(width: 38, height: 38)
                    .background(.thinMaterial, in: Circle())
            }
            VStack(alignment: .leading, spacing: 1) {
                Text("VeloCut").font(.headline.weight(.semibold))
                Text(model.clips.isEmpty ? "Новый проект" : "\(model.clips.count) клип. • \(format(model.projectDuration))")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            PhotosPicker(selection: $photoItems, maxSelectionCount: 20, matching: .videos) {
                Image(systemName: "photo.on.rectangle.angled").frame(width: 34, height: 34)
            }
            Button { model.isFileImporting = true } label: {
                Image(systemName: "folder").frame(width: 34, height: 34)
            }
            Button { inspector = .export } label: {
                Text("Экспорт")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 14)
                    .frame(height: 36)
                    .background(Color.accentColor, in: Capsule())
                    .foregroundStyle(.white)
            }
            .disabled(model.clips.isEmpty)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(.ultraThinMaterial)
    }

    private var previewArea: some View {
        GeometryReader { geometry in
            ZStack {
                RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Color.black)
                if !model.clips.isEmpty {
                    PlayerView(player: model.player)
                        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                    if !model.overlayText.isEmpty {
                        Text(model.overlayText)
                            .font(.system(size: model.overlayTextSize, weight: .bold, design: .rounded))
                            .multilineTextAlignment(.center)
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.9), radius: 4, y: 2)
                            .padding(.horizontal, 24)
                            .position(x: geometry.size.width / 2, y: geometry.size.height * model.overlayTextY)
                    }
                } else {
                    VStack(spacing: 14) {
                        Image(systemName: "film.stack").font(.system(size: 42, weight: .medium)).foregroundStyle(.white)
                        Text("Добавить видео").font(.headline).foregroundStyle(.white)
                        HStack(spacing: 10) {
                            PhotosPicker(selection: $photoItems, maxSelectionCount: 20, matching: .videos) {
                                Label("Фото", systemImage: "photo.on.rectangle")
                                    .padding(.horizontal, 14).frame(height: 38)
                                    .background(.white, in: Capsule()).foregroundStyle(.black)
                            }
                            Button { model.isFileImporting = true } label: {
                                Label("Файлы", systemImage: "folder")
                                    .padding(.horizontal, 14).frame(height: 38)
                                    .background(.ultraThinMaterial, in: Capsule()).foregroundStyle(.white)
                            }
                        }
                    }
                }
            }
            .overlay(alignment: .topTrailing) {
                if model.isPreviewCaching {
                    HStack(spacing: 6) { ProgressView().controlSize(.mini); Text("Кеш") }
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 9).padding(.vertical, 6)
                        .background(.ultraThinMaterial, in: Capsule()).padding(10)
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 8)
    }

    private var playbackBar: some View {
        HStack(spacing: 12) {
            Button { model.undo() } label: { Image(systemName: "arrow.uturn.backward") }.disabled(!model.canUndo)
            Button { model.redo() } label: { Image(systemName: "arrow.uturn.forward") }.disabled(!model.canRedo)
            Divider().frame(height: 22)
            Button { model.seek(by: -10) } label: { Image(systemName: "gobackward.10") }
            Button { model.playPause() } label: {
                Image(systemName: model.isPlaying ? "pause.fill" : "play.fill")
                    .font(.title3)
                    .frame(width: 46, height: 36)
                    .background(.thinMaterial, in: Capsule())
            }
            Button { model.seek(by: 10) } label: { Image(systemName: "goforward.10") }
            Menu {
                Picker("Воспроизведение", selection: $model.playbackMode) {
                    ForEach(PlaybackMode.allCases) { mode in Label(mode.rawValue, systemImage: mode.icon).tag(mode) }
                }
                Toggle("Вернуть ползунок к старту", isOn: $model.returnPlayheadAfterStop)
            } label: {
                Image(systemName: model.playbackMode.icon)
                    .frame(width: 34, height: 34)
                    .background(.thinMaterial, in: Circle())
            }
            Spacer(minLength: 4)
            Text("\(formatPrecise(model.projectTime)) / \(formatPrecise(model.projectDuration))")
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .disabled(model.clips.isEmpty)
    }

    private var timelineArea: some View {
        VStack(spacing: 6) {
            HStack(spacing: 10) {
                Label("Таймлайн", systemImage: "timeline.selection").font(.caption.weight(.semibold))
                if model.isPreviewCaching { ProgressView().controlSize(.mini) }
                Spacer()
                PhotosPicker(selection: $photoItems, maxSelectionCount: 20, matching: .videos) {
                    Image(systemName: "photo.badge.plus")
                }
                Button { model.isFileImporting = true } label: { Image(systemName: "plus") }
                Button { model.timelineZoom = max(0.55, model.timelineZoom - 0.2) } label: { Image(systemName: "minus.magnifyingglass") }
                Button { model.timelineZoom = min(3.2, model.timelineZoom + 0.2) } label: { Image(systemName: "plus.magnifyingglass") }
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 14)

            GeometryReader { geo in
                let pps = 34.0 * model.timelineZoom
                let center = geo.size.width / 2
                let rulerHeight: CGFloat = 24
                let laneHeight: CGFloat = 50
                ZStack(alignment: .topLeading) {
                    RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color(uiColor: .secondarySystemGroupedBackground))

                    TimelineRuler(projectTime: model.projectTime, duration: model.projectDuration, pointsPerSecond: pps)
                        .frame(height: rulerHeight)

                    ForEach(0..<3, id: \.self) { lane in
                        let y = rulerHeight + CGFloat(lane) * laneHeight
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(lane == 0 ? Color.secondary.opacity(0.08) : Color.secondary.opacity(0.045))
                            .frame(height: laneHeight - 4)
                            .padding(.horizontal, 4)
                            .position(x: geo.size.width / 2, y: y + laneHeight / 2)
                        Text("V\(lane + 1)")
                            .font(.system(size: 9, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5).padding(.vertical, 3)
                            .background(.thinMaterial, in: Capsule())
                            .position(x: 20, y: y + 12)
                    }

                    ForEach(Array(model.clips.enumerated()), id: \.element.id) { index, clip in
                        let start = model.projectStart(of: clip.id)
                        let width = max(54, clip.outputDuration * pps)
                        let x = center + (start - model.projectTime) * pps + width / 2
                        let y = rulerHeight + CGFloat(clip.track) * laneHeight + laneHeight / 2
                        TimelineClipCard(clip: clip, index: index, selected: clip.id == model.selectedClipID, width: width, onTap: {
                            model.selectClip(clip.id)
                        }, onLongPressMenu: {
                            model.selectedClipID = clip.id
                            contextClipID = clip.id
                            clipActionPresented = true
                        }, onMove: { translation in
                            model.moveClip(clip.id, translation: translation, pointsPerSecond: pps)
                        })
                        .position(x: x, y: y)
                    }

                    Rectangle()
                        .fill(Color.accentColor)
                        .frame(width: 2)
                        .position(x: center, y: geo.size.height / 2)
                        .allowsHitTesting(false)

                    Button { model.splitAtPlayhead() } label: {
                        Image(systemName: "scissors")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 30, height: 30)
                            .background(Color.accentColor, in: Circle())
                            .shadow(radius: 3, y: 1)
                    }
                    .position(x: center, y: rulerHeight + 4)
                    .disabled(model.clips.isEmpty)
                }
                .clipped()
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            if timelineDragStart == nil {
                                timelineDragStart = model.projectTime
                                model.beginScrub()
                            }
                            let start = timelineDragStart ?? model.projectTime
                            model.scrub(to: start - Double(value.translation.width) / pps)
                        }
                        .onEnded { _ in
                            timelineDragStart = nil
                            model.endScrub()
                        }
                )
            }
            .frame(minHeight: 174)
            .padding(.horizontal, 8)
        }
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .padding(.horizontal, 8)
    }

    private var bottomToolBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 5) {
                editorTool("scissors", "Обрезка", .trim)
                editorTool("speedometer", "Скорость", .speed)
                editorTool("waveform", "Аудио", .audio)
                editorTool("textformat", "Текст", .text)
                editorTool("camera.filters", "Фильтры", .filters)
                editorTool("slider.horizontal.3", "Настройка", .adjust)
                editorTool("wand.and.stars", "Улучшить", .enhance)
            }
            .padding(.horizontal, 10)
        }
        .padding(.vertical, 7)
        .background(.ultraThinMaterial)
        .disabled(model.clips.isEmpty)
    }

    private var exportOverlay: some View {
        ZStack {
            Color.black.opacity(0.28).ignoresSafeArea()
            VStack(spacing: 14) {
                ProgressView(value: model.exportProgress).progressViewStyle(.linear).frame(width: 220)
                Text("Экспорт \(Int(model.exportProgress * 100))%").font(.headline)
                Text("Не закрывайте VeloCut").font(.caption).foregroundStyle(.secondary)
            }
            .padding(24)
            .background(.ultraThickMaterial, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        }
    }

    private func loadPhotoItems(_ items: [PhotosPickerItem]) {
        guard !items.isEmpty else { return }
        Task {
            var urls: [URL] = []
            for item in items {
                do {
                    if let movie = try await item.loadTransferable(type: PickedMovie.self) { urls.append(movie.url) }
                } catch {
                    await MainActor.run { model.errorMessage = "Не удалось импортировать видео из Фото: \(error.localizedDescription)" }
                }
            }
            await MainActor.run {
                model.importVideos(urls)
                photoItems = []
            }
        }
    }

    private func editorTool(_ icon: String, _ title: String, _ tool: InspectorTool) -> some View {
        Button { inspector = tool; model.haptic(.selection) } label: {
            VStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 17, weight: .medium)).frame(height: 22)
                Text(title).font(.caption2)
            }
            .frame(width: 72, height: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func format(_ seconds: Double) -> String {
        let value = max(0, Int(seconds.rounded()))
        return String(format: "%d:%02d", value / 60, value % 60)
    }

    private func formatPrecise(_ seconds: Double) -> String {
        let safe = max(0, seconds)
        let minutes = Int(safe) / 60
        let secs = safe - Double(minutes * 60)
        return String(format: "%d:%04.1f", minutes, secs)
    }
}

struct TimelineRuler: View {
    let projectTime: Double
    let duration: Double
    let pointsPerSecond: Double

    var body: some View {
        Canvas { context, size in
            guard pointsPerSecond > 0 else { return }
            let visibleHalf = Double(size.width / 2) / pointsPerSecond
            let start = max(0, floor(projectTime - visibleHalf) - 1)
            let end = min(max(duration, projectTime + visibleHalf), ceil(projectTime + visibleHalf) + 1)
            if end < start { return }
            var second = Int(start)
            while Double(second) <= end {
                let x = size.width / 2 + CGFloat((Double(second) - projectTime) * pointsPerSecond)
                var path = Path()
                path.move(to: CGPoint(x: x, y: 13))
                path.addLine(to: CGPoint(x: x, y: 22))
                context.stroke(path, with: .color(.secondary.opacity(0.45)), lineWidth: 1)
                if second % 2 == 0 {
                    let text = context.resolve(Text(formatTime(Double(second))).font(.system(size: 8, design: .monospaced)).foregroundStyle(.secondary))
                    context.draw(text, at: CGPoint(x: x + 3, y: 4), anchor: .topLeading)
                }
                second += 1
            }
        }
    }

    private func formatTime(_ seconds: Double) -> String {
        let value = max(0, Int(seconds))
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

struct TimelineClipCard: View {
    let clip: EditorClip
    let index: Int
    let selected: Bool
    let width: Double
    let onTap: () -> Void
    let onLongPressMenu: () -> Void
    let onMove: (CGSize) -> Void

    @State private var dragTranslation: CGSize = .zero
    @State private var didHold = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(selected ? Color.accentColor.opacity(0.25) : Color.secondary.opacity(0.14))
            HStack(spacing: 2) {
                ForEach(0..<max(2, Int(width / 28)), id: \.self) { _ in
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.secondary.opacity(0.18))
                        .overlay { Image(systemName: "play.rectangle.fill").font(.system(size: 8)).foregroundStyle(.secondary) }
                }
            }
            .padding(4)
            VStack(spacing: 0) {
                HStack {
                    Text("\(index + 1)").font(.system(size: 8, weight: .bold)).padding(.horizontal, 4).padding(.vertical, 2).background(.ultraThinMaterial, in: Capsule())
                    Spacer()
                    Text("\(clip.speed, specifier: "%g")×").font(.system(size: 8, weight: .semibold))
                }
                Spacer()
                HStack {
                    Text(clip.name).font(.system(size: 8, weight: .medium)).lineLimit(1)
                    Spacer()
                    Text(format(clip.outputDuration)).font(.system(size: 8, design: .monospaced))
                }
            }
            .padding(5)
        }
        .frame(width: width, height: 42)
        .overlay { RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(selected ? Color.accentColor : Color.clear, lineWidth: 2) }
        .offset(dragTranslation)
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
        .highPriorityGesture(
            LongPressGesture(minimumDuration: 0.34)
                .sequenced(before: DragGesture(minimumDistance: 0))
                .onChanged { value in
                    switch value {
                    case .first(true):
                        if !didHold {
                            didHold = true
                            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                        }
                    case .second(true, let drag):
                        if let drag { dragTranslation = drag.translation }
                    default: break
                    }
                }
                .onEnded { value in
                    defer { dragTranslation = .zero; didHold = false }
                    switch value {
                    case .second(true, let drag):
                        guard let drag else { onLongPressMenu(); return }
                        let distance = hypot(drag.translation.width, drag.translation.height)
                        if distance < 10 { onLongPressMenu() }
                        else { onMove(drag.translation) }
                    case .first(true):
                        onLongPressMenu()
                    default: break
                    }
                }
        )
    }

    private func format(_ seconds: Double) -> String {
        let value = max(0, Int(seconds.rounded()))
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

struct InspectorSheet: View {
    let tool: InspectorTool
    @ObservedObject var model: EditorViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                switch tool {
                case .trim: trimView
                case .speed: speedView
                case .audio: audioView
                case .text: textView
                case .filters: filtersView
                case .adjust: adjustView
                case .enhance: enhanceView
                case .export: exportView
                }
            }
            .padding(.horizontal, 18)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Готово") { dismiss() } } }
        }
    }

    private var title: String {
        switch tool {
        case .trim: return "Обрезка"
        case .speed: return "Скорость"
        case .audio: return "Аудио"
        case .text: return "Текст"
        case .filters: return "Фильтры"
        case .adjust: return "Настройка"
        case .enhance: return "Улучшение"
        case .export: return "Экспорт"
        }
    }

    private var trimView: some View {
        VStack(spacing: 22) {
            if let clip = model.selectedClip {
                valueSlider(title: "Начало", value: Binding(get: { model.selectedClip?.trimStart ?? 0 }, set: { model.setTrimStart($0) }), range: 0...max(0.1, clip.duration), suffix: time(model.selectedClip?.trimStart ?? 0))
                valueSlider(title: "Конец", value: Binding(get: { model.selectedClip?.trimEnd ?? clip.duration }, set: { model.setTrimEnd($0) }), range: 0...max(0.1, clip.duration), suffix: time(model.selectedClip?.trimEnd ?? clip.duration))
                HStack { Label("После обрезки", systemImage: "clock"); Spacer(); Text(time(clip.outputDuration)).monospacedDigit() }
                    .font(.subheadline).foregroundStyle(.secondary)
                Text("Split находится прямо на синем playhead таймлайна.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.top, 18)
    }

    private var speedView: some View {
        VStack(spacing: 20) {
            Text("\(model.selectedClip?.speed ?? 1, specifier: "%.2f")×").font(.system(size: 38, weight: .semibold, design: .rounded))
            Slider(value: Binding(get: { model.selectedClip?.speed ?? 1 }, set: { model.setSpeed($0) }), in: 0.1...5, step: 0.05)
            HStack {
                ForEach([0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0], id: \.self) { value in
                    Button("\(value, specifier: "%g")×") { model.setSpeed(value) }
                        .font(.caption.weight(.semibold)).buttonStyle(.bordered)
                        .tint(abs((model.selectedClip?.speed ?? 1) - value) < 0.001 ? .accentColor : .secondary)
                }
            }
            Label("Скорость меняет длительность видео и звука синхронно.", systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.top, 18)
    }

    private var audioView: some View {
        VStack(spacing: 20) {
            valueSlider(title: "Громкость клипа", value: Binding(get: { model.selectedClip?.volume ?? 1 }, set: { model.setVolume($0) }), range: 0...2, suffix: "\(Int((model.selectedClip?.volume ?? 1) * 100))%")
            Divider()
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Музыка").font(.headline)
                    Text(model.musicName ?? "Не добавлена").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Button(model.musicURL == nil ? "Добавить" : "Заменить") { model.isAudioImporting = true }.buttonStyle(.borderedProminent)
            }
            if model.musicURL != nil {
                valueSlider(title: "Громкость музыки", value: $model.musicVolume, range: 0...1.5, suffix: "\(Int(model.musicVolume * 100))%")
            }
            Spacer()
        }
        .padding(.top, 18)
    }

    private var textView: some View {
        VStack(spacing: 18) {
            TextField("Введите текст", text: $model.overlayText, axis: .vertical)
                .textFieldStyle(.roundedBorder).lineLimit(1...3).onTapGesture { model.registerUndo() }
            valueSlider(title: "Размер", value: $model.overlayTextSize, range: 18...72, suffix: "\(Int(model.overlayTextSize))")
            valueSlider(title: "Положение", value: $model.overlayTextY, range: 0.15...0.9, suffix: "")
            HStack {
                ForEach([(0.2, "Верх"), (0.5, "Центр"), (0.82, "Низ")], id: \.0) { item in
                    Button(item.1) { model.overlayTextY = item.0 }.buttonStyle(.bordered)
                }
            }
            Spacer()
        }
        .padding(.top, 18)
    }

    private var filtersView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(EditorFilter.allCases) { filter in
                    Button { model.setFilter(filter) } label: {
                        VStack(spacing: 8) {
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(.thinMaterial).frame(width: 86, height: 86)
                                .overlay { Image(systemName: filter.systemImage).font(.system(size: 30)) }
                                .overlay { RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(model.selectedFilter == filter ? Color.accentColor : Color.clear, lineWidth: 3) }
                            Text(filter.rawValue).font(.caption)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 20)
        }
    }

    private var adjustView: some View {
        VStack(spacing: 20) {
            valueSlider(title: "Яркость", value: Binding(get: { model.brightness }, set: { model.updateColor(brightness: $0) }), range: -0.35...0.35, suffix: "\(Int(model.brightness * 100))")
            valueSlider(title: "Контраст", value: Binding(get: { model.contrast }, set: { model.updateColor(contrast: $0) }), range: 0.5...1.7, suffix: "\(Int((model.contrast - 1) * 100))")
            valueSlider(title: "Насыщенность", value: Binding(get: { model.saturation }, set: { model.updateColor(saturation: $0) }), range: 0...2, suffix: "\(Int((model.saturation - 1) * 100))")
            Button("Сбросить настройки") { model.resetColor() }.buttonStyle(.bordered)
            Spacer()
        }
        .padding(.top, 18)
    }

    private var enhanceView: some View {
        VStack(spacing: 20) {
            Image(systemName: "wand.and.stars.inverse").font(.system(size: 42)).symbolRenderingMode(.hierarchical).foregroundStyle(Color.accentColor)
            Text("Локальное улучшение").font(.title3.weight(.semibold))
            Text("Изменения кешируются с задержкой 120 мс, поэтому таймлайн продолжает быстро скраббиться.").font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            valueSlider(title: "Интенсивность", value: Binding(get: { model.enhanceAmount }, set: { model.setEnhance($0) }), range: 0...1, suffix: "\(Int(model.enhanceAmount * 100))%")
            Spacer()
        }
        .padding(.top, 18)
    }

    private var exportView: some View {
        VStack(spacing: 18) {
            Picker("Качество", selection: $model.exportQuality) {
                ForEach(ExportQuality.allCases) { quality in Text(quality.rawValue).tag(quality) }
            }
            .pickerStyle(.segmented)
            VStack(spacing: 12) {
                exportRow("Длительность", time(model.projectDuration))
                exportRow("Клипы", "\(model.clips.count)")
                exportRow("Фильтр", model.selectedFilter.rawValue)
                exportRow("Текст", model.overlayText.isEmpty ? "Нет" : "Да")
                exportRow("Музыка", model.musicURL == nil ? "Нет" : "Да")
            }
            .padding(16)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            Button { dismiss(); model.exportProject() } label: {
                Label("Экспортировать \(model.exportQuality.rawValue)", systemImage: "square.and.arrow.up")
                    .font(.headline).frame(maxWidth: .infinity).frame(height: 48)
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.isExporting || model.clips.isEmpty)
            Spacer()
        }
        .padding(.top, 18)
    }

    private func valueSlider(title: String, value: Binding<Double>, range: ClosedRange<Double>, suffix: String) -> some View {
        VStack(spacing: 8) {
            HStack {
                Text(title).font(.subheadline.weight(.medium))
                Spacer()
                if !suffix.isEmpty { Text(suffix).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
            }
            Slider(value: value, in: range)
        }
    }

    private func exportRow(_ title: String, _ value: String) -> some View {
        HStack { Text(title).foregroundStyle(.secondary); Spacer(); Text(value).fontWeight(.medium) }.font(.subheadline)
    }

    private func time(_ seconds: Double) -> String {
        let value = max(0, Int(seconds.rounded()))
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

struct ProjectInfoSheet: View {
    @ObservedObject var model: EditorViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Проект") {
                    LabeledContent("Клипы", value: "\(model.clips.count)")
                    LabeledContent("Длительность", value: format(model.projectDuration))
                    LabeledContent("Качество экспорта", value: model.exportQuality.rawValue)
                    LabeledContent("Кеш превью", value: "rev. \(model.cacheRevision)")
                }
                Section("Воспроизведение") {
                    LabeledContent("Режим", value: model.playbackMode.rawValue)
                    Toggle("Возвращать playhead", isOn: $model.returnPlayheadAfterStop)
                }
            }
            .navigationTitle("Проект")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Готово") { dismiss() } } }
        }
    }

    private func format(_ seconds: Double) -> String {
        let value = max(0, Int(seconds.rounded()))
        return String(format: "%d:%02d", value / 60, value % 60)
    }
}

@main
struct VeloCutAIApp: App {
    var body: some Scene {
        WindowGroup { EditorView().tint(.blue) }
    }
}
