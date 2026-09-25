import Foundation
import AVFoundation
import CoreVideo
import RifeMetal

enum VeloCutAIQuality: String, CaseIterable, Identifiable {
    case fast = "Fast"
    case balanced = "Balanced"
    case hq = "HQ"

    var id: String { rawValue }

    var rifeTier: RifeQualityTier {
        switch self {
        case .fast: return .fast
        case .balanced: return .balanced
        case .hq: return .hq
        }
    }
}

enum VeloCutRIFEError: LocalizedError {
    case noVideoTrack
    case readerStart
    case writerStart
    case noFrames
    case appendFailed
    case interpolationFailed(String)
    case muxFailed(String)

    var errorDescription: String? {
        switch self {
        case .noVideoTrack: return "RIFE: видеодорожка не найдена"
        case .readerStart: return "RIFE: не удалось запустить декодирование"
        case .writerStart: return "RIFE: не удалось запустить AI-рендер"
        case .noFrames: return "RIFE: в видео нет кадров для интерполяции"
        case .appendFailed: return "RIFE: не удалось записать интерполированный кадр"
        case .interpolationFailed(let text): return "RIFE: \(text)"
        case .muxFailed(let text): return "RIFE audio: \(text)"
        }
    }
}

enum VeloCutRIFEProcessor {
    static func interpolateVideo(
        inputURL: URL,
        factor: Int,
        quality: VeloCutAIQuality,
        progress: @escaping @Sendable (Double) -> Void
    ) async throws -> URL {
        let safeFactor = factor >= 4 ? 4 : 2
        return try await Task.detached(priority: .userInitiated) {
            try render(inputURL: inputURL, factor: safeFactor, quality: quality, progress: progress)
        }.value
    }

    private static func render(
        inputURL: URL,
        factor: Int,
        quality: VeloCutAIQuality,
        progress: @escaping @Sendable (Double) -> Void
    ) throws -> URL {
        let asset = AVURLAsset(url: inputURL)
        guard let sourceTrack = asset.tracks(withMediaType: .video).first else {
            throw VeloCutRIFEError.noVideoTrack
        }

        let naturalSize = sourceTrack.naturalSize
        let width = max(2, Int(abs(naturalSize.width).rounded()))
        let height = max(2, Int(abs(naturalSize.height).rounded()))
        let sourceFPS = max(1, Double(sourceTrack.nominalFrameRate))
        let targetFPS = min(120.0, sourceFPS * Double(factor))
        let durationSeconds = max(0.001, CMTimeGetSeconds(asset.duration))

        let videoOnlyURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("VeloCut-RIFE-video-\(UUID().uuidString).mp4")
        try? FileManager.default.removeItem(at: videoOnlyURL)

        let reader = try AVAssetReader(asset: asset)
        let readerOutput = AVAssetReaderTrackOutput(
            track: sourceTrack,
            outputSettings: [
                kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
                kCVPixelBufferMetalCompatibilityKey as String: true
            ]
        )
        readerOutput.alwaysCopiesSampleData = false
        guard reader.canAdd(readerOutput) else { throw VeloCutRIFEError.readerStart }
        reader.add(readerOutput)

        let writer = try AVAssetWriter(outputURL: videoOnlyURL, fileType: .mp4)
        let bitRate = min(
            80_000_000,
            max(8_000_000, Int(Double(width * height) * targetFPS * 0.15))
        )
        let writerInput = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: width,
                AVVideoHeightKey: height,
                AVVideoCompressionPropertiesKey: [
                    AVVideoAverageBitRateKey: bitRate,
                    AVVideoExpectedSourceFrameRateKey: Int(targetFPS.rounded()),
                    AVVideoMaxKeyFrameIntervalKey: max(1, Int(targetFPS.rounded() * 2))
                ]
            ]
        )
        writerInput.expectsMediaDataInRealTime = false
        writerInput.transform = sourceTrack.preferredTransform

        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: writerInput,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
                kCVPixelBufferWidthKey as String: width,
                kCVPixelBufferHeightKey as String: height,
                kCVPixelBufferMetalCompatibilityKey as String: true,
                kCVPixelBufferIOSurfacePropertiesKey as String: [:] as [String: Any]
            ]
        )

        guard writer.canAdd(writerInput) else { throw VeloCutRIFEError.writerStart }
        writer.add(writerInput)
        guard writer.startWriting() else {
            throw writer.error ?? VeloCutRIFEError.writerStart
        }
        guard reader.startReading() else {
            writer.cancelWriting()
            throw reader.error ?? VeloCutRIFEError.readerStart
        }
        writer.startSession(atSourceTime: .zero)

        let interpolator: RifeInterpolator
        do {
            interpolator = try RifeInterpolator(configuration: .bundled(qualityTier: quality.rifeTier))
        } catch {
            reader.cancelReading()
            writer.cancelWriting()
            throw VeloCutRIFEError.interpolationFailed(error.localizedDescription)
        }

        func waitUntilReady() throws {
            while !writerInput.isReadyForMoreMediaData {
                if writer.status == .failed { throw writer.error ?? VeloCutRIFEError.appendFailed }
                Thread.sleep(forTimeInterval: 0.001)
            }
        }

        func append(_ buffer: CVPixelBuffer, at time: CMTime) throws {
            try waitUntilReady()
            guard adaptor.append(buffer, withPresentationTime: time) else {
                throw writer.error ?? VeloCutRIFEError.appendFailed
            }
        }

        guard let firstSample = readerOutput.copyNextSampleBuffer(),
              let firstBuffer = CMSampleBufferGetImageBuffer(firstSample) else {
            reader.cancelReading()
            writer.cancelWriting()
            throw VeloCutRIFEError.noFrames
        }

        var previousBuffer: CVPixelBuffer = firstBuffer
        var previousPTS = CMSampleBufferGetPresentationTimeStamp(firstSample)
        if previousPTS < .zero { previousPTS = .zero }
        try append(previousBuffer, at: previousPTS)

        while let sample = readerOutput.copyNextSampleBuffer() {
            autoreleasepool {
                // Keep the loop's temporary AV/CoreVideo objects short-lived.
            }
            guard let currentBuffer = CMSampleBufferGetImageBuffer(sample) else { continue }
            let currentPTS = CMSampleBufferGetPresentationTimeStamp(sample)
            let delta = CMTimeSubtract(currentPTS, previousPTS)

            if delta > .zero {
                let timesteps: [Float] = factor == 4 ? [0.25, 0.5, 0.75] : [0.5]
                do {
                    let generated = try interpolator.interpolate(
                        previous: previousBuffer,
                        current: currentBuffer,
                        timesteps: timesteps
                    )
                    for (index, frame) in generated.enumerated() {
                        let fraction = Double(index + 1) / Double(factor)
                        let offset = CMTimeMultiplyByFloat64(delta, multiplier: fraction)
                        try append(frame, at: CMTimeAdd(previousPTS, offset))
                    }
                } catch {
                    reader.cancelReading()
                    writer.cancelWriting()
                    throw VeloCutRIFEError.interpolationFailed(error.localizedDescription)
                }
            }

            try append(currentBuffer, at: currentPTS)
            previousBuffer = currentBuffer
            previousPTS = currentPTS
            progress(min(0.96, max(0, CMTimeGetSeconds(currentPTS) / durationSeconds)))
        }

        guard reader.status == .completed else {
            writer.cancelWriting()
            throw reader.error ?? VeloCutRIFEError.readerStart
        }

        writerInput.markAsFinished()
        let semaphore = DispatchSemaphore(value: 0)
        writer.finishWriting { semaphore.signal() }
        semaphore.wait()
        guard writer.status == .completed else {
            throw writer.error ?? VeloCutRIFEError.writerStart
        }

        progress(0.97)
        return try muxOriginalAudio(videoURL: videoOnlyURL, originalURL: inputURL, progress: progress)
    }

    private static func muxOriginalAudio(
        videoURL: URL,
        originalURL: URL,
        progress: @escaping @Sendable (Double) -> Void
    ) throws -> URL {
        let videoAsset = AVURLAsset(url: videoURL)
        let originalAsset = AVURLAsset(url: originalURL)
        guard let videoSource = videoAsset.tracks(withMediaType: .video).first else {
            throw VeloCutRIFEError.noVideoTrack
        }

        let composition = AVMutableComposition()
        guard let videoTrack = composition.addMutableTrack(
            withMediaType: .video,
            preferredTrackID: kCMPersistentTrackID_Invalid
        ) else {
            throw VeloCutRIFEError.muxFailed("не удалось создать видеодорожку")
        }

        let videoDuration = videoAsset.duration
        try videoTrack.insertTimeRange(
            CMTimeRange(start: .zero, duration: videoDuration),
            of: videoSource,
            at: .zero
        )
        videoTrack.preferredTransform = videoSource.preferredTransform

        if let audioSource = originalAsset.tracks(withMediaType: .audio).first,
           let audioTrack = composition.addMutableTrack(
                withMediaType: .audio,
                preferredTrackID: kCMPersistentTrackID_Invalid
           ) {
            let audioDuration = originalAsset.duration
            let duration = CMTimeMinimum(videoDuration, audioDuration)
            if duration > .zero {
                try audioTrack.insertTimeRange(
                    CMTimeRange(start: .zero, duration: duration),
                    of: audioSource,
                    at: .zero
                )
            }
        }

        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("VeloCut-AI-\(UUID().uuidString).mp4")
        try? FileManager.default.removeItem(at: outputURL)

        let compatible = AVAssetExportSession.exportPresets(compatibleWith: composition)
        let preset = compatible.contains(AVAssetExportPresetPassthrough)
            ? AVAssetExportPresetPassthrough
            : AVAssetExportPresetHighestQuality
        guard let session = AVAssetExportSession(asset: composition, presetName: preset) else {
            throw VeloCutRIFEError.muxFailed("не удалось создать export session")
        }
        session.outputURL = outputURL
        session.outputFileType = .mp4
        session.shouldOptimizeForNetworkUse = true

        let semaphore = DispatchSemaphore(value: 0)
        session.exportAsynchronously { semaphore.signal() }
        semaphore.wait()
        guard session.status == .completed else {
            throw VeloCutRIFEError.muxFailed(session.error?.localizedDescription ?? "неизвестная ошибка")
        }
        progress(1)
        return outputURL
    }
}
