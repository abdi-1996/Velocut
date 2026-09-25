import SwiftUI
import AVFoundation
import Accelerate

struct VeloCutBeatMarker: Identifiable, Equatable, Sendable {
    let id: UUID
    let time: Double
    let strength: Double
    let isStrong: Bool

    init(id: UUID = UUID(), time: Double, strength: Double, isStrong: Bool) {
        self.id = id
        self.time = time
        self.strength = strength
        self.isStrong = isStrong
    }
}

struct VeloCutBeatResult: Sendable {
    let bpm: Double
    let markers: [VeloCutBeatMarker]
}

enum VeloCutAudioTools {
    static func extractAudio(from videoURL: URL) async throws -> URL {
        let asset = AVURLAsset(url: videoURL)
        guard let sourceAudio = try await asset.loadTracks(withMediaType: .audio).first else {
            throw NSError(domain: "VeloCut.Audio", code: 101, userInfo: [NSLocalizedDescriptionKey: "В выбранном видео нет аудиодорожки"])
        }
        let composition = AVMutableComposition()
        guard let audioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw NSError(domain: "VeloCut.Audio", code: 102, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать аудиодорожку"])
        }
        let duration = try await asset.load(.duration)
        try audioTrack.insertTimeRange(CMTimeRange(start: .zero, duration: duration), of: sourceAudio, at: .zero)
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-Extracted-\(UUID().uuidString).m4a")
        try? FileManager.default.removeItem(at: output)
        guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetAppleM4A) else {
            throw NSError(domain: "VeloCut.Audio", code: 103, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать экспорт аудио"])
        }
        session.outputURL = output; session.outputFileType = .m4a; session.shouldOptimizeForNetworkUse = true
        await withCheckedContinuation { continuation in session.exportAsynchronously { continuation.resume() } }
        guard session.status == .completed else {
            throw session.error ?? NSError(domain: "VeloCut.Audio", code: 104, userInfo: [NSLocalizedDescriptionKey: "Извлечение аудио не завершено"])
        }
        return output
    }

    static func detectBeats(in audioURL: URL, sensitivity: Double) async throws -> VeloCutBeatResult {
        try await Task.detached(priority: .userInitiated) { try detectBeatsSync(in: audioURL, sensitivity: sensitivity) }.value
    }

    private static func detectBeatsSync(in audioURL: URL, sensitivity: Double) throws -> VeloCutBeatResult {
        let file = try AVAudioFile(forReading: audioURL)
        let format = file.processingFormat
        let sampleRate = format.sampleRate
        let channelCount = Int(format.channelCount)
        guard sampleRate > 0, channelCount > 0 else { throw NSError(domain:"VeloCut.Beat",code:201,userInfo:[NSLocalizedDescriptionKey:"Неподдерживаемый формат аудио"]) }
        let windowFrames=1024
        guard let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:AVAudioFrameCount(windowFrames)) else { throw NSError(domain:"VeloCut.Beat",code:202,userInfo:[NSLocalizedDescriptionKey:"Не удалось создать PCM-буфер"]) }
        var envelope:[Float]=[]; envelope.reserveCapacity(max(1,Int(file.length)/windowFrames+1))
        while file.framePosition < file.length {
            let remaining=file.length-file.framePosition; let count=AVAudioFrameCount(min(Int64(windowFrames),remaining)); try file.read(into:buffer,frameCount:count)
            let frames=Int(buffer.frameLength); guard frames>0 else{break}; guard let channels=buffer.floatChannelData else{throw NSError(domain:"VeloCut.Beat",code:203,userInfo:[NSLocalizedDescriptionKey:"Beat Detector требует PCM Float32"])}
            var energy:Float=0
            for channel in 0..<channelCount { var mean:Float=0; vDSP_meamgv(channels[channel],1,&mean,vDSP_Length(frames)); energy += mean }
            envelope.append(energy/Float(channelCount))
        }
        guard envelope.count>8 else{throw NSError(domain:"VeloCut.Beat",code:204,userInfo:[NSLocalizedDescriptionKey:"Аудио слишком короткое для анализа"])}
        var flux=[Float](repeating:0,count:envelope.count); for i in 1..<envelope.count{flux[i]=max(0,envelope[i]-envelope[i-1])}
        let rate=sampleRate/Double(windowFrames), sens=min(max(sensitivity,0.05),1), mult=Float(2.45-sens*1.25), radius=max(3,Int(rate*0.18)), minDist=max(2,Int(rate*0.16))
        var candidates:[(index:Int,time:Double,value:Float)] = []
        var last = -minDist
        if flux.count>2 { for i in 1..<(flux.count-1){ let lo=max(0,i-radius),hi=min(flux.count,i+radius+1); var sum:Float=0; for j in lo..<hi{sum += flux[j]}; let threshold=max(0.00001,(sum/Float(max(1,hi-lo)))*mult); guard flux[i]>=threshold,flux[i]>=flux[i-1],flux[i]>=flux[i+1] else{continue}; if i-last<minDist{if let prev=candidates.last,flux[i]>prev.value{candidates[candidates.count-1]=(i,Double(i)/rate,flux[i]);last=i};continue};candidates.append((i,Double(i)/rate,flux[i]));last=i } }
        let lagMin=max(1,Int((60/200.0)*rate)),lagMax=min(flux.count/2,max(lagMin+1,Int((60/60.0)*rate)));var bestLag=0,bestScore = -Double.infinity
        if lagMax>=lagMin{for lag in lagMin...lagMax{var score=0.0,count=0;for i in lag..<flux.count{score += Double(flux[i]*flux[i-lag]);count+=1};if count>0{score/=Double(count)};if score>bestScore{bestScore=score;bestLag=lag}}}
        var bpm=bestLag>0 ? 60*rate/Double(bestLag):0;while bpm>0&&bpm<70{bpm*=2};while bpm>190{bpm/=2}
        if !bpm.isFinite||bpm<=0{let intervals=zip(candidates.dropFirst(),candidates).map{$0.0.time-$0.1.time}.filter{$0>0.2&&$0<1.2}.sorted();if !intervals.isEmpty{bpm=60/intervals[intervals.count/2];while bpm<70{bpm*=2};while bpm>190{bpm/=2}}}
        guard bpm.isFinite,bpm>=40,bpm<=240 else{throw NSError(domain:"VeloCut.Beat",code:205,userInfo:[NSLocalizedDescriptionKey:"Не удалось уверенно определить BPM"])}
        let duration=Double(file.length)/sampleRate,interval=60/bpm,maxFlux=max(candidates.map(\.value).max() ?? 0.00001,0.00001)
        if candidates.isEmpty{var markers:[VeloCutBeatMarker]=[],t=0.0;var i=0;while t<=duration{markers.append(.init(time:t,strength:i%4==0 ? 1:0.45,isStrong:i%4==0));t+=interval;i+=1};return .init(bpm:bpm,markers:markers)}
        let anchor=candidates.filter{$0.time<=min(duration,8)}.max(by:{$0.value<$1.value}) ?? candidates[0];var phase=anchor.time;while phase-interval>=0{phase-=interval}
        var markers:[VeloCutBeatMarker]=[],grid=phase;var gridIndex=0;let snapWindow=min(0.14,interval*0.32)
        while grid<=duration+0.001{var chosen=grid,strength=0.35;if let nearest=candidates.min(by:{abs($0.time-grid)<abs($1.time-grid)}),abs(nearest.time-grid)<=snapWindow{chosen=nearest.time;strength=min(1,max(0.15,Double(nearest.value/maxFlux)))};let strong=gridIndex%4==0||strength>=0.88;markers.append(.init(time:chosen,strength:strength,isStrong:strong));grid+=interval;gridIndex+=1}
        return .init(bpm:bpm,markers:markers)
    }
}

struct BeatTimelineMarkersV49: View {
    let markers:[VeloCutBeatMarker]; let projectTime:Double; let pps:Double; let center:CGFloat; let height:CGFloat
    var body: some View {
        ZStack(alignment:.topLeading){
            ForEach(markers){marker in
                Circle()
                    .fill(Color.orange.opacity(marker.isStrong ? 0.95 : 0.68))
                    .frame(width:marker.isStrong ? 6:4,height:marker.isStrong ? 6:4)
                    .position(x:center+CGFloat((marker.time-projectTime)*pps),y:marker.isStrong ? 7:8)
            }
        }.allowsHitTesting(false).clipped()
    }
}
