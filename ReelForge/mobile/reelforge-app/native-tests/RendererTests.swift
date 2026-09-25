import XCTest
import AVFoundation
import UIKit
@testable import RendererHost
final class RendererTests: XCTestCase {
 override func setUp() { super.setUp(); executionTimeAllowance = 120 }
 func fixture(_ folder: URL) async throws -> (URL,URL) {
  let video = folder.appendingPathComponent("input.mp4"), audio = folder.appendingPathComponent("music.wav")
  let writer = try AVAssetWriter(outputURL: video, fileType: .mp4)
  let input = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 180, AVVideoHeightKey: 320])
  let adapter = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,kCVPixelBufferWidthKey as String:180,kCVPixelBufferHeightKey as String:320])
  writer.add(input); XCTAssertTrue(writer.startWriting()); writer.startSession(atSourceTime: .zero)
  for frame in 0..<90 {
   while !input.isReadyForMoreMediaData { try await Task.sleep(nanoseconds: 1_000_000) }
   var pixel: CVPixelBuffer?
   CVPixelBufferPoolCreatePixelBuffer(nil, adapter.pixelBufferPool!, &pixel)
   CVPixelBufferLockBaseAddress(pixel!, [])
   let bytes = CVPixelBufferGetBaseAddress(pixel!)!.assumingMemoryBound(to: UInt8.self)
   let stride = CVPixelBufferGetBytesPerRow(pixel!)
   for y in 0..<320 { for x in 0..<180 {
     let p=y*stride+x*4;bytes[p]=255;bytes[p+1]=UInt8(frame*2);bytes[p+2]=UInt8(x);bytes[p+3]=UInt8(y%256)
   }}
   CVPixelBufferUnlockBaseAddress(pixel!, [])
   XCTAssertTrue(adapter.append(pixel!, withPresentationTime: CMTime(value: Int64(frame), timescale: 30)))
  }
  input.markAsFinished();await withCheckedContinuation { (c:CheckedContinuation<Void,Never>) in writer.finishWriting { c.resume() } }
  XCTAssertEqual(writer.status,.completed)
  let format=AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 1)!
  let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:264600)!;buffer.frameLength=264600
  for i in 0..<264600 { buffer.floatChannelData![0][i]=Float(sin(Double(i)*2*Double.pi*440/44100)*0.3) }
  let file=try AVAudioFile(forWriting:audio,settings:format.settings);try file.write(from:buffer)
  return (video,audio)
 }
 func testOfflineTemplates() async throws {
  let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
  defer { try? FileManager.default.removeItem(at:folder) }
  let (video,music)=try await fixture(folder)
  for template in ["clean","velocity","flash","cinema","zoom"] {
   let result=try await ReelEngine().render(["clips":[video.absoluteString],"music":music.absoluteString,"mode":"music","template":template,"duration":5,"bpm":120,"quality":"720","captions":"manual","text":"Привет мир\nНа телефоне"],progress:{p,m in print("RENDER \(p) \(m)")})
   let url=URL(string:result["uri"] as! String)!, asset=AVURLAsset(url:url)
   defer { try? FileManager.default.removeItem(at:url) }
   let tracks=try await asset.loadTracks(withMediaType:.video)
   let size=try await tracks[0].load(.naturalSize)
   let renderedDuration=try await asset.load(.duration).seconds
   XCTAssertEqual(size,CGSize(width:720,height:1280));XCTAssertEqual(renderedDuration,5,accuracy:0.15)
   let audioTracks=try await asset.loadTracks(withMediaType:.audio)
   XCTAssertFalse(audioTracks.isEmpty)
   let generator=AVAssetImageGenerator(asset:asset);generator.appliesPreferredTrackTransform=true
   let image=try generator.copyCGImage(at:CMTime(seconds:1,preferredTimescale:600),actualTime:nil)
   let attachment=XCTAttachment(image:UIImage(cgImage:image));attachment.name=template;attachment.lifetime = .keepAlways;add(attachment)
  }
 }
 func testSpeechPauseCutAndManualText() async throws {
  let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
  defer { try? FileManager.default.removeItem(at:folder) }
  let (video,music)=try await fixture(folder);let mix=AVMutableComposition()
  let v=AVURLAsset(url:video),a=AVURLAsset(url:music)
  try mix.addMutableTrack(withMediaType:.video,preferredTrackID:kCMPersistentTrackID_Invalid)!.insertTimeRange(CMTimeRange(start:.zero,duration:CMTime(seconds:3,preferredTimescale:600)),of:v.tracks(withMediaType:.video)[0],at:.zero)
  try mix.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid)!.insertTimeRange(CMTimeRange(start:.zero,duration:CMTime(seconds:3,preferredTimescale:600)),of:a.tracks(withMediaType:.audio)[0],at:.zero)
  let source=folder.appendingPathComponent("talk.mp4");let export=AVAssetExportSession(asset:mix,presetName:AVAssetExportPresetHighestQuality)!
  export.outputURL=source;export.outputFileType = .mp4
  await withCheckedContinuation { (c:CheckedContinuation<Void,Never>) in export.exportAsynchronously { c.resume() } }
  XCTAssertEqual(export.status,.completed)
  let result=try await ReelEngine().render(["clips":[source.absoluteString],"mode":"speech","duration":5,"captions":"manual","text":"Тест"],progress:{p,m in print("RENDER \(p) \(m)")})
  let url=URL(string:result["uri"] as! String)!;defer { try? FileManager.default.removeItem(at:url) }
  XCTAssertGreaterThan(result["duration"] as! Double,2.5)
  let audioTracks=try await AVURLAsset(url:url).loadTracks(withMediaType:.audio)
  XCTAssertFalse(audioTracks.isEmpty)
 }
}
