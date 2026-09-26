import AVFoundation
import CoreImage
import UIKit
import Vision

struct ReelTextTexture {
  let start: Double
  let end: Double
  let image: CIImage
  @MainActor init(caption: ReelCaption, size: CGSize, editorial: Bool = false) {
    start = caption.start; end = caption.end
    let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = false
    let canvas = CGSize(width: size.width-70, height: editorial ? size.height*0.28 : size.height*0.18)
    let renderer = UIGraphicsImageRenderer(size: canvas, format: format)
    let uiImage = renderer.image { _ in
      let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
      let fontSize = min(size.width*0.09,size.height*0.17)
      let font = editorial ? (UIFont(name:"Didot",size:fontSize) ?? UIFont.systemFont(ofSize:fontSize)) : UIFont.boldSystemFont(ofSize:min(size.width,size.height)*0.06)
      let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.white, .strokeColor: UIColor.black, .strokeWidth: editorial ? 0 : -4, .paragraphStyle: paragraph]
      (caption.text as NSString).draw(in: CGRect(origin: .zero, size: canvas), withAttributes: attrs)
    }
    image = CIImage(cgImage: uiImage.cgImage!).transformed(by: CGAffineTransform(translationX: 35, y: editorial ? size.height*0.40 : size.height*0.13))
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
  let intensity: Double
  let depthText: Bool
  init(range: CMTimeRange, visuals: [ReelVisual], template: String, size: CGSize, captions: [ReelTextTexture], flashes: [Double], intensity: Double = 0.65, depthText: Bool = false) {
    timeRange = range; self.visuals = visuals; self.template = template; self.size = size; self.captions = captions; self.flashes = flashes
    self.intensity = intensity; self.depthText = depthText
    requiredSourceTrackIDs = visuals.map { NSNumber(value: $0.track.trackID) }
  }
}
final class ReelVideoCompositor: NSObject, AVVideoCompositing {
  let sourcePixelBufferAttributes: [String: Any]? = [kCVPixelBufferPixelFormatTypeKey as String: [kCVPixelFormatType_32BGRA]]
  let requiredPixelBufferAttributesForRenderContext: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferIOSurfacePropertiesKey as String: [:]]
  private let queue = DispatchQueue(label: "reelforge.frames")
  private let context = CIContext(options: [.cacheIntermediates: false])
  private var renderContext: AVVideoCompositionRenderContext?
  private let stateLock = NSLock()
  private var generation = 0
  func renderContextChanged(_ newRenderContext: AVVideoCompositionRenderContext) {
    stateLock.lock(); renderContext = newRenderContext; stateLock.unlock()
  }
  private func opacity(_ image: CIImage, _ value: Double) -> CIImage {
    let a = CGFloat(max(0,min(1,value)))
    return image.applyingFilter("CIColorMatrix", parameters: ["inputRVector":CIVector(x:a,y:0,z:0,w:0),"inputGVector":CIVector(x:0,y:a,z:0,w:0),"inputBVector":CIVector(x:0,y:0,z:a,w:0),"inputAVector":CIVector(x:0,y:0,z:0,w:a)])
  }
  private lazy var redCube: Data = {
    let n = 32; var values = [Float](); values.reserveCapacity(n*n*n*4)
    for b in 0..<n { for g in 0..<n { for r in 0..<n {
      let rf = Float(r)/31, gf = Float(g)/31, bf = Float(b)/31
      let grey = 0.2126*rf+0.7152*gf+0.0722*bf
      let difference = rf-max(gf,bf)
      let keep = min(1,max(0,(difference-0.04)/0.16))
      values += [grey+(rf-grey)*keep,grey+(gf-grey)*keep,grey+(bf-grey)*keep,1]
    }}}
    return values.withUnsafeBytes { Data($0) }
  }()
  func personMask(_ image: CIImage, bounds: CGRect) throws -> CIImage? {
    // Analyze each caption frame to avoid stale masks on fast movement or cuts.
    let scale = min(1,512/max(bounds.width,bounds.height))
    let small = image.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
    let request = VNGeneratePersonSegmentationRequest()
    request.qualityLevel = .balanced; request.outputPixelFormat = kCVPixelFormatType_OneComponent8
    try VNImageRequestHandler(ciImage:small,options:[:]).perform([request])
    guard let buffer = request.results?.first?.pixelBuffer else { return nil }
    let mask = CIImage(cvPixelBuffer:buffer)
    return mask.transformed(by:CGAffineTransform(scaleX:bounds.width/mask.extent.width,y:bounds.height/mask.extent.height)).cropped(to:bounds)
  }
  func startRequest(_ request: AVAsynchronousVideoCompositionRequest) {
    stateLock.lock(); let currentGeneration = generation; stateLock.unlock()
    queue.async { autoreleasepool {
      self.stateLock.lock(); let context = self.renderContext; let cancelled = self.generation != currentGeneration; self.stateLock.unlock()
      if cancelled { request.finishCancelledRequest(); return }
      guard let instruction = request.videoCompositionInstruction as? ReelCIInstruction, let output = context?.newPixelBuffer() else {
        request.finish(with: NSError(domain:"ReelForge",code:2,userInfo:[NSLocalizedDescriptionKey:"Не удалось создать видеокадр"])); return
      }
      let size = instruction.size; let bounds = CGRect(origin:.zero,size:size); let t = request.compositionTime.seconds
      var frame = CIImage(color:CIColor.black).cropped(to:bounds)
      let start = instruction.timeRange.start.seconds, length = instruction.timeRange.duration.seconds
      let p = max(0,min(1,(t-start)/max(length,0.001)))
      for (index, visual) in instruction.visuals.enumerated() {
        guard let source = request.sourceFrame(byTrackID:visual.track.trackID) else { continue }
        var transform = visual.transform; var alpha = 1.0
        let local = max(0,t-visual.start), duration = max(0.01,visual.end-visual.start)
        let action = instruction.template == "hero", red = instruction.template == "redline"
        var pulse = 0.0
        if action || red {
          pulse = exp(-local/(action ? 0.13 : 0.28))*instruction.intensity
          let scale = 1+(action ? 0.14 : 0.055)*pulse+0.025*min(1,local/duration)
          let angle = action ? sin(local*49)*0.018*pulse : 0
          let dx = action ? sin(local*83)*size.width*0.012*pulse : 0
          let dy = action ? cos(local*67)*size.height*0.008*pulse : 0
          transform = transform.concatenating(CGAffineTransform(translationX:-size.width/2,y:-size.height/2))
            .concatenating(CGAffineTransform(scaleX:scale,y:scale)).concatenating(CGAffineTransform(rotationAngle:angle))
            .concatenating(CGAffineTransform(translationX:size.width/2+dx,y:size.height/2+dy))
        }
        if instruction.visuals.count == 2 {
          let incoming = index == 1
          alpha = incoming ? p : 1
          if instruction.template == "hero" { alpha = incoming ? min(1,p*2) : 1 }
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
        var image = CIImage(cvPixelBuffer:source).clampedToExtent().transformed(by:flipSource.concatenating(transform).concatenating(flipOutput)).cropped(to:bounds)
        if (action || red) && pulse > 0.06 {
          image = image.clampedToExtent().applyingFilter("CIMotionBlur",parameters:["inputRadius":pulse*(action ? 13 : 7),"inputAngle":action ? 0.15 : 0]).cropped(to:bounds)
        }
        frame = self.opacity(image,alpha).composited(over:frame)
      }
      let analysisFrame = frame
      if instruction.template == "redline" {
        frame = frame.applyingFilter("CIColorCube",parameters:["inputCubeDimension":32,"inputCubeData":self.redCube])
          .applyingFilter("CIColorControls",parameters:["inputContrast":1.12,"inputBrightness":-0.025])
      } else if instruction.template == "hero" {
        frame = frame.applyingFilter("CIColorControls",parameters:["inputContrast":1.10,"inputSaturation":0.9])
      }
      if ["hero","redline"].contains(instruction.template) {
        frame = frame.applyingFilter("CIVignette",parameters:["inputIntensity":0.25*instruction.intensity,"inputRadius":min(size.width,size.height)*0.6])
      }
      for flash in instruction.flashes where t >= flash && t < flash+0.18 {
        let a = (instruction.template == "hero" ? 0.18*instruction.intensity : 0.9)*(1-abs((t-flash)/0.09-1))
        frame = CIImage(color:CIColor(red:1,green:1,blue:1,alpha:a)).cropped(to:bounds).composited(over:frame)
      }
      let foreground = frame
      let activeCaptions = instruction.captions.filter { t >= $0.start && t < $0.end }
      var mask: CIImage?
      if instruction.depthText && !activeCaptions.isEmpty {
        do { mask = try self.personMask(analysisFrame,bounds:bounds) }
        catch {
          request.finish(with:NSError(domain:"ReelForge",code:3,userInfo:[NSLocalizedDescriptionKey:"Маска человека недоступна на этом устройстве. Выключите «Текст за человеком» и повторите экспорт."])); return
        }
      }
      for caption in activeCaptions where t >= caption.start && t < caption.end {
        let fade = min(1,min((t-caption.start)/0.07,(caption.end-t)/0.07))
        var title = caption.image
        if instruction.template == "redline" {
          let enter = min(1,(t-caption.start)/0.22)
          title = title.transformed(by:CGAffineTransform(translationX:0,y:-(1-enter)*size.height*0.04))
        }
        frame = self.opacity(title,fade).composited(over:frame)
      }
      if let mask = mask {
        frame = foreground.applyingFilter("CIBlendWithMask",parameters:[kCIInputBackgroundImageKey:frame,kCIInputMaskImageKey:mask])
      }
      self.context.render(frame.cropped(to:bounds),to:output,bounds:bounds,colorSpace:CGColorSpace(name:CGColorSpace.sRGB))
      request.finish(withComposedVideoFrame:output)
    }}
  }
  func cancelAllPendingVideoCompositionRequests() { stateLock.lock(); generation += 1; stateLock.unlock() }
}
