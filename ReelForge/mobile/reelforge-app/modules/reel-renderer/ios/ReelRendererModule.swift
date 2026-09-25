import ExpoModulesCore
import UIKit
import Speech

public class ReelRendererModule: Module {
  private let engine = ReelEngine()
  public func definition() -> ModuleDefinition {
    Name("ReelRenderer")
    Events("progress")
    Function("capabilities") { (language: String) -> [String: Any] in
      let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language))
      return ["local": true, "speech": recognizer?.supportsOnDeviceRecognition ?? false]
    }
    AsyncFunction("render") { (options: [String: Any]) async throws -> [String: Any] in
      await MainActor.run { UIApplication.shared.isIdleTimerDisabled = true }
      defer { Task { @MainActor in UIApplication.shared.isIdleTimerDisabled = false } }
      let result = try await self.engine.render(options) { value, message in
        self.sendEvent("progress", ["value": value, "message": message])
      }
      return result
    }
    Function("cancel") { self.engine.cancel() }
    OnDestroy { self.engine.cancel() }
  }
}
