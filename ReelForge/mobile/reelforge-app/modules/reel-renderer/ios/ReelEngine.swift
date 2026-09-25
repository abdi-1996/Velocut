import Foundation
import AVFoundation
import Speech
import UIKit
import QuartzCore

private func tm(_ seconds: Double) -> CMTime { CMTime(seconds: seconds, preferredTimescale: 30000) }
private func fail(_ text: String) -> NSError { NSError(domain: "ReelForge", code: 1, userInfo: [NSLocalizedDescriptionKey: text]) }
struct ReelCaption { let start: Double; let end: Double; let text: String }
struct ReelSpan { let start: Double; let end: Double }
struct ReelVisual {
  let track: AVMutableCompositionTrack
  let transform: CGAffineTransform
  let start: Double
  let end: Double
}

public final class ReelEngine {
  private let lock = NSLock()
  private var stopped = false
  private var busy = false
  private var exporter: AVAssetExportSession?
  private var speechTask: SFSpeechRecognitionTask?
  private func locked<T>(_ action: () -> T) -> T { lock.lock(); defer { lock.unlock() }; return action() }
  public init() {}
  public func cancel() {
    let pair = locked { () -> (AVAssetExportSession?, SFSpeechRecognitionTask?) in
      stopped = true; return (exporter, speechTask)
    }
    pair.0?.cancelExport(); pair.1?.cancel()
  }
  private func check() throws { if locked({ stopped }) { throw fail("Монтаж отменён") } }
  private func localURL(_ string: String) throws -> URL {
    guard let url = URL(string: string), url.isFileURL, FileManager.default.fileExists(atPath: url.path) else {
      throw fail("Исходник недоступен. Выберите видео или музыку заново.")
    }
    return url
  }
  private func fit(_ source: AVAssetTrack, _ size: CGSize) -> CGAffineTransform {
    let rect = CGRect(origin: .zero, size: source.naturalSize).applying(source.preferredTransform)
    let scale = max(size.width / abs(rect.width), size.height / abs(rect.height))
    return source.preferredTransform
      .concatenating(CGAffineTransform(translationX: -rect.minX, y: -rect.minY))
      .concatenating(CGAffineTransform(scaleX: scale, y: scale))
      .concatenating(CGAffineTransform(translationX: (size.width-abs(rect.width)*scale)/2, y: (size.height-abs(rect.height)*scale)/2))
  }
  // Decode only the selected interval; memory is bounded to scalar energy samples.
  private func energies(_ asset: AVAsset, limit: Double) throws -> [(Double, Double)] {
    guard let track = asset.tracks(withMediaType: .audio).first else { throw fail("В файле нет звуковой дорожки") }
    let reader = try AVAssetReader(asset: asset)
    reader.timeRange = CMTimeRange(start: .zero, duration: tm(limit))
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsNonInterleaved: false])
    guard reader.canAdd(output) else { throw fail("Не удалось декодировать звук") }
    reader.add(output); guard reader.startReading() else { throw reader.error ?? fail("Ошибка чтения звука") }
    var values: [(Double, Double)] = []
    while let buffer = output.copyNextSampleBuffer() {
      try check()
      guard let block = CMSampleBufferGetDataBuffer(buffer) else { continue }
      let count = CMBlockBufferGetDataLength(block) / MemoryLayout<Float>.size
      var samples = [Float](repeating: 0, count: count)
      let status = samples.withUnsafeMutableBytes { bytes in
        CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: bytes.count, destination: bytes.baseAddress!)
      }
      guard status == kCMBlockBufferNoErr, count > 0 else { continue }
      let square = samples.reduce(0.0) { $0 + Double($1) * Double($1) }
      values.append((CMSampleBufferGetPresentationTimeStamp(buffer).seconds, sqrt(square / Double(count))))
    }
    if reader.status == .failed { throw reader.error ?? fail("Ошибка декодирования") }
    return values
  }
  private func cuts(_ music: AVAsset, total: Double, bpm: Double) throws -> [Double] {
    let values = try energies(music, limit: total)
    var result = [0.0]; var position = 240 / bpm
    while position < total - 0.65 {
      var best = position; var strength = 0.0
      for i in 1..<max(1, values.count) where abs(values[i].0-position) < 0.18 {
        let onset = values[i].1-values[i-1].1
        if onset > strength { strength = onset; best = values[i].0 }
      }
      if best-result.last! > 0.65 && total-best > 0.65 { result.append(best) }
      position += 240 / bpm
    }
    result.append(total); return result
  }
  private func silenceSpans(_ asset: AVAsset, limit: Double) throws -> [ReelSpan] {
    let values = try energies(asset, limit: limit)
    let threshold = max(0.008, (values.map { $0.1 }.max() ?? 0) * 0.055)
    var spans: [ReelSpan] = []
    for (time, energy) in values where energy > threshold {
      let start = max(0, time-0.1); let end = min(limit, time+0.14)
      if let last = spans.last, start-last.end < 0.3 {
        spans[spans.count-1] = ReelSpan(start: last.start, end: end)
      } else { spans.append(ReelSpan(start: start, end: end)) }
    }
    return spans.filter { $0.end-$0.start >= 0.12 }
  }
  private func recognize(_ url: URL, language: String, limit: Double) async throws -> [ReelCaption] {
    guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language)), recognizer.supportsOnDeviceRecognition else {
      throw fail("Для этого языка нет офлайн-распознавания iOS. Выберите ручной текст или режим без субтитров.")
    }
    let permission = await withCheckedContinuation { (c: CheckedContinuation<SFSpeechRecognizerAuthorizationStatus, Never>) in
      SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0) }
    }
    guard permission == .authorized else { throw fail("Разрешите распознавание речи в настройках iOS или выберите ручной текст.") }
    try check()
    let request = SFSpeechURLRecognitionRequest(url: url)
    request.requiresOnDeviceRecognition = true
    request.shouldReportPartialResults = false
    return try await withCheckedThrowingContinuation { continuation in
      let completion = ReelRecognitionCompletion(continuation)
      let task = recognizer.recognitionTask(with: request) { result, error in
        if let result = result, result.isFinal {
          completion.finish(.success(result.bestTranscription.segments.filter { $0.timestamp < limit }.map {
            ReelCaption(start: $0.timestamp, end: min(limit, $0.timestamp+$0.duration), text: $0.substring)
          }))
        } else if let error = error { completion.finish(.failure(error)) }
      }
      locked { speechTask = task }
      DispatchQueue.global().asyncAfter(deadline: .now()+100) {
        if completion.finish(.failure(fail("Офлайн-распознавание не завершилось. Попробуйте ручной текст."))) { task.cancel() }
      }
    }
  }
  public func render(_ options: [String: Any], progress: @escaping (Double, String) -> Void) async throws -> [String: Any] {
    guard locked({ if busy { return false }; busy = true; stopped = false; return true }) else { throw fail("Монтаж уже запущен") }
    defer { locked { busy = false; exporter = nil; speechTask = nil } }
    let clips = options["clips"] as? [String] ?? []
    guard !clips.isEmpty && clips.count <= 12 else { throw fail("Выберите от 1 до 12 видео") }
    let assets = try clips.map { AVURLAsset(url: try localURL($0)) }
    let speech = options["mode"] as? String == "speech"
    let template = options["template"] as? String ?? "clean"
    let duration = min(60, max(5, (options["duration"] as? NSNumber)?.doubleValue ?? 15))
    let bpm = min(200, max(60, (options["bpm"] as? NSNumber)?.doubleValue ?? 120))
    let size = options["quality"] as? String == "1080" ? CGSize(width: 1080, height: 1920) : CGSize(width: 720, height: 1280)
    let composition = AVMutableComposition()
    var plan: [(AVAsset, Double, Double)] = []
    var captions: [ReelCaption] = []; var music: AVAsset?
    progress(0.02, speech ? "Анализ речи на iPhone" : "Анализ музыки на iPhone")
    let captionMode = options["captions"] as? String ?? "none"
    if speech {
      let asset = assets[0]; let limit = min(duration, asset.duration.seconds)
      guard limit.isFinite && limit > 0.2 else { throw fail("Видео слишком короткое") }
      var spans: [ReelSpan]
      var words: [ReelCaption] = []
      if captionMode == "auto" {
        // Extract only the selected audio interval before recognition, never upload.
        let audioURL = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".m4a")
        defer { try? FileManager.default.removeItem(at: audioURL) }
        guard let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else { throw fail("Невозможно прочитать звук") }
        session.outputURL = audioURL; session.outputFileType = .m4a
        session.timeRange = CMTimeRange(start: .zero, duration: tm(limit))
        try await export(session, progress: { _, _ in })
        words = try await recognize(audioURL, language: options["language"] as? String ?? "ru-RU", limit: limit)
        guard !words.isEmpty else { throw fail("Речь не найдена") }
        spans = []
        for word in words {
          if let last = spans.last, word.start-last.end < 0.35 {
            spans[spans.count-1] = ReelSpan(start: last.start, end: min(limit, word.end+0.1))
          } else { spans.append(ReelSpan(start: max(0, word.start-0.08), end: min(limit, word.end+0.1))) }
        }
      } else { spans = try silenceSpans(asset, limit: limit) }
      guard !spans.isEmpty else { throw fail("Звук не найден или слишком тихий") }
      var timeline = 0.0
      for span in spans {
        let length = span.end-span.start
        plan.append((asset, span.start, length))
        let local = words.filter { $0.start >= span.start && $0.start < span.end }
        for index in stride(from: 0, to: local.count, by: 4) {
          let group = Array(local[index..<min(index+4, local.count)])
          captions.append(ReelCaption(start: timeline+group[0].start-span.start, end: timeline+group.last!.end-span.start, text: group.map { $0.text }.joined(separator: " ")))
        }
        timeline += length
      }
    } else {
      music = AVURLAsset(url: try localURL(options["music"] as? String ?? ""))
      let total = min(duration, music!.duration.seconds)
      guard total.isFinite && total > 0.7 else { throw fail("Музыка слишком короткая") }
      let boundaries = try cuts(music!, total: total, bpm: bpm)
      for i in 0..<boundaries.count-1 {
        plan.append((assets[i % assets.count], 0, boundaries[i+1]-boundaries[i]+(i < boundaries.count-2 ? 0.18 : 0)))
      }
    }
    try check()
    var visuals: [ReelVisual] = []; var cursor = 0.0
    let overlap = speech ? 0.0 : 0.18
    for (index, item) in plan.enumerated() {
      try check()
      let (asset, sourceStart, outputDuration) = item
      guard let source = asset.tracks(withMediaType: .video).first, asset.duration.seconds.isFinite, asset.duration.seconds > 0.1,
            let track = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else { throw fail("Не удалось прочитать видео") }
      let start = cursor
      if !speech && ["velocity", "zoom"].contains(template) {
        var outputTime = 0.0; var sourceTime = 0.0
        // 30 speed samples per second. Splits are exact on the composition timebase.
        while outputTime < outputDuration-0.00001 {
          try check()
          let step = min(1.0/30, outputDuration-outputTime)
          let rate = 1.25-0.75*cos(2*Double.pi*outputTime/outputDuration)
          var remainOutput = step
          while remainOutput > 0.00001 {
            if sourceTime >= asset.duration.seconds-0.0001 { sourceTime = 0 }
            let sourceLength = min(remainOutput*rate, asset.duration.seconds-sourceTime)
            let scaled = sourceLength/rate
            let at = tm(start+outputTime+step-remainOutput)
            try track.insertTimeRange(CMTimeRange(start: tm(sourceTime), duration: tm(sourceLength)), of: source, at: at)
            track.scaleTimeRange(CMTimeRange(start: at, duration: tm(sourceLength)), toDuration: tm(scaled))
            sourceTime += sourceLength; remainOutput -= scaled
          }
          outputTime += step
        }
      } else {
        var remaining = outputDuration; var at = start; var sourceTime = sourceStart
        while remaining > 0.00001 {
          try check()
          let length = min(remaining, asset.duration.seconds-sourceTime)
          guard length > 0 else { throw fail("Некорректная длительность видео") }
          try track.insertTimeRange(CMTimeRange(start: tm(sourceTime), duration: tm(length)), of: source, at: tm(at))
          remaining -= length; at += length; sourceTime = 0
        }
      }
      if speech, let sourceAudio = asset.tracks(withMediaType: .audio).first,
         let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
        try audio.insertTimeRange(CMTimeRange(start: tm(sourceStart), duration: tm(outputDuration)), of: sourceAudio, at: tm(start))
      }
      visuals.append(ReelVisual(track: track, transform: fit(source, size), start: start, end: start+outputDuration))
      cursor = start+outputDuration-(index < plan.count-1 ? overlap : 0)
      progress(0.08+Double(index+1)/Double(plan.count)*0.2, "Подготовка клипа \(index+1)/\(plan.count)")
    }
    let total = cursor
    if let music = music, let source = music.tracks(withMediaType: .audio).first,
       let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
      try audio.insertTimeRange(CMTimeRange(start: .zero, duration: tm(min(total,music.duration.seconds))), of: source, at: .zero)
    }
    if captionMode == "manual", let text = options["text"] as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      let lines = text.components(separatedBy: .newlines).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
      captions = lines.enumerated().map { i, line in ReelCaption(start: total*Double(i)/Double(lines.count), end: total*Double(i+1)/Double(lines.count), text: String(line.prefix(120))) }
    }
    let vc = AVMutableVideoComposition()
    vc.renderSize = size; vc.frameDuration = CMTime(value: 1, timescale: 30)
    vc.colorPrimaries = AVVideoColorPrimaries_ITU_R_709_2
    vc.colorTransferFunction = AVVideoTransferFunction_ITU_R_709_2
    vc.colorYCbCrMatrix = AVVideoYCbCrMatrix_ITU_R_709_2
    let textures = await MainActor.run { captions.map { ReelTextTexture(caption: $0, size: size) } }
    let points = Array(Set([0.0, total]+visuals.flatMap { [$0.start, $0.end] })).sorted()
    vc.customVideoCompositorClass = ReelVideoCompositor.self
    vc.instructions = (0..<points.count-1).compactMap { index in
      let a = points[index], b = points[index+1]
      guard b-a > 0.00001 else { return nil }
      let active = visuals.filter { $0.start <= (a+b)/2 && $0.end > (a+b)/2 }
      return ReelCIInstruction(range: CMTimeRange(start: tm(a), end: tm(b)), visuals: active, template: template, size: size, captions: textures, flashes: template == "flash" ? visuals.dropFirst().map { $0.start } : [])
    }
    let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("ReelForge", isDirectory: true)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let output = folder.appendingPathComponent("ReelForge-\(UUID().uuidString).mp4")
    guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else { throw fail("Невозможно создать экспорт") }
    session.videoComposition = vc; session.outputURL = output; session.outputFileType = .mp4; session.shouldOptimizeForNetworkUse = true
    session.timeRange = CMTimeRange(start: .zero, duration: tm(total))
    do { try await export(session, progress: progress) }
    catch { try? FileManager.default.removeItem(at: output); throw error }
    try check(); progress(1, "Готово — сохранено на телефоне")
    return ["uri": output.absoluteString, "duration": total, "width": size.width, "height": size.height]
  }
  private func export(_ session: AVAssetExportSession, progress: @escaping (Double, String) -> Void) async throws {
    try check(); locked { exporter = session }
    let monitor = Task {
      while !Task.isCancelled {
        progress(0.3+Double(session.progress)*0.69, "Экспорт на iPhone")
        try? await Task.sleep(nanoseconds: 250_000_000)
      }
    }
    defer { monitor.cancel(); locked { exporter = nil } }
    if #available(iOS 18.0, *) {
      try await session.export(to: session.outputURL!, as: session.outputFileType!)
    } else {
      await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in session.exportAsynchronously { c.resume() } }
      guard session.status == .completed else { throw session.error ?? fail("Не удалось экспортировать видео") }
    }
    try check()
  }
}
private final class ReelRecognitionCompletion {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<[ReelCaption], Error>?
  init(_ continuation: CheckedContinuation<[ReelCaption], Error>) { self.continuation = continuation }
  @discardableResult func finish(_ result: Result<[ReelCaption], Error>) -> Bool {
    lock.lock(); let value = continuation; continuation = nil; lock.unlock()
    guard let value = value else { return false }; value.resume(with: result); return true
  }
}
