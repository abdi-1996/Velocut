import AVFoundation
import CoreImage
import UIKit

struct ReelTextTexture {
  let start: Double
  let end: Double
  let image: CIImage
  @MainActor init(caption: ReelCaption, size: CGSize) {
    start = caption.start; end = caption.end
    let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = false
    let canvas = CGSize(width: size.width-70, height: size.height*0.15)
    let renderer = UIGraphicsImageRenderer(size: canvas, format: format)
    let uiImage = renderer.image { _ in
      let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
      let attrs: [NSAttributedString.Key: Any] = [.font: UIFont.boldSystemFont(ofSize: size.width*0.06), .foregroundColor: UIColor.white, .strokeColor: UIColor.black, .strokeWidth: -4, .paragraphStyle: paragraph]
      (caption.text as NSString).draw(in: CGRect(origin: .zero, size: canvas), withAttributes: attrs)
    }
    image = CIImage(cgImage: uiImage.cgImage!).transformed(by: CGAffineTransform(translationX: 35, y: size.height*0.18))
  }
}
final class ReelCIInstruction: NSObject, AVVideoCompositionInstructionProtocol {
  let timeRange: CMTimeRange
  let enablePostProcessing = true
  let containsTweening = true
  let requiredSourceTrackIDs: [NSValue]?
  let passthroughTrackID = kCMPersistentTrackID_Invalid
  let visuals: [ReelVisual]
  let template: String
  let size: CGSize
  let captions: [ReelTextTexture]
  let flashes: [Double]
  init(range: CMTimeRange, visuals: [ReelVisual], template: String, size: CGSize, captions: [ReelTextTexture], flashes: [Double]) {
    timeRange = range; self.visuals = visuals; self.template = template; self.size = size; self.captions = captions; self.flashes = flashes
    requiredSourceTrackIDs = visuals.map { NSNumber(value: $0.track.trackID) }
  }
}
final class ReelVideoCompositor: NSObject, AVVideoCompositing {
  let sourcePixelBufferAttributes: [String: Any]? = [kCVPixelBufferPixelFormatTypeKey as String: [kCVPixelFormatType_32BGRA]]
  let requiredPixelBufferAttributesForRenderContext: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferIOSurfacePropertiesKey as String: [:]]
  private let queue = DispatchQueue(label: "reelforge.frames")
  private let context = CIContext(options: [.cacheIntermediates: false])
  private var renderContext: AVVideoCompositionRenderContext?
  func renderContextChanged(_ newRenderContext: AVVideoCompositionRenderContext) { queue.sync { renderContext = newRenderContext } }
  private func opacity(_ image: CIImage, _ value: Double) -> CIImage {
    let a = CGFloat(max(0,min(1,value)))
    return image.applyingFilter("CIColorMatrix", parameters: ["inputRVector":CIVector(x:a,y:0,z:0,w:0),"inputGVector":CIVector(x:0,y:a,z:0,w:0),"inputBVector":CIVector(x:0,y:0,z:a,w:0),"inputAVector":CIVector(x:0,y:0,z:0,w:a)])
  }
  func startRequest(_ request: AVAsynchronousVideoCompositionRequest) {
    queue.async { autoreleasepool {
      guard let instruction = request.videoCompositionInstruction as? ReelCIInstruction, let output = self.renderContext?.newPixelBuffer() else {
        request.finish(with: NSError(domain:"ReelForge",code:2,userInfo:[NSLocalizedDescriptionKey:"Не удалось создать видеокадр"])); return
      }
      let size = instruction.size; let bounds = CGRect(origin:.zero,size:size); let t = request.compositionTime.seconds
      var frame = CIImage(color:CIColor.black).cropped(to:bounds)
      let start = instruction.timeRange.start.seconds, length = instruction.timeRange.duration.seconds
      let p = max(0,min(1,(t-start)/max(length,0.001)))
      for (index, visual) in instruction.visuals.enumerated() {
        guard let source = request.sourceFrame(byTrackID:visual.track.trackID) else { continue }
        var transform = visual.transform; var alpha = 1.0
        if instruction.visuals.count == 2 {
          let incoming = index == 1
          alpha = incoming ? p : 1
          if instruction.template == "cinema" { alpha = incoming ? max(0,2*p-1) : max(0,1-2*p) }
          if instruction.template == "velocity" {
            transform = transform.concatenating(CGAffineTransform(translationX: size.width*CGFloat(incoming ? 1-p : -p),y:0))
          } else if instruction.template == "zoom" && incoming {
            let scale = 1+0.25*(1-p)
            transform = transform.concatenating(CGAffineTransform(a:scale,b:0,c:0,d:scale,tx:size.width*(1-scale)/2,ty:size.height*(1-scale)/2))
          }
        }
        // Convert AVFoundation's top-left transform into Core Image's bottom-left coordinates.
        let flipSource = CGAffineTransform(a:1,b:0,c:0,d:-1,tx:0,ty:CGFloat(CVPixelBufferGetHeight(source)))
        let flipOutput = CGAffineTransform(a:1,b:0,c:0,d:-1,tx:0,ty:size.height)
        let image = CIImage(cvPixelBuffer:source).transformed(by:flipSource.concatenating(transform).concatenating(flipOutput)).cropped(to:bounds)
        frame = self.opacity(image,alpha).composited(over:frame)
      }
      for flash in instruction.flashes where t >= flash && t < flash+0.18 {
        let a = 0.9*(1-abs((t-flash)/0.09-1))
        frame = CIImage(color:CIColor(red:1,green:1,blue:1,alpha:a)).cropped(to:bounds).composited(over:frame)
      }
      for caption in instruction.captions where t >= caption.start && t < caption.end {
        let fade = min(1,min((t-caption.start)/0.07,(caption.end-t)/0.07))
        frame = self.opacity(caption.image,fade).composited(over:frame)
      }
      self.context.render(frame.cropped(to:bounds),to:output,bounds:bounds,colorSpace:CGColorSpace(name:CGColorSpace.sRGB))
      request.finish(withComposedVideoFrame:output)
    }}
  }
  func cancelAllPendingVideoCompositionRequests() { queue.sync {} }
}
