import Foundation

struct SavedSpeedCurve: Identifiable, Codable, Equatable {
    var id: UUID = UUID()
    var name: String
    var curve: SpeedCurve
}

extension EditorViewModel {
    private var savedCurveStorageKey: String { "VeloCut.savedSpeedCurves.v1" }

    var savedCurves: [SavedSpeedCurve] {
        guard let data = UserDefaults.standard.data(forKey: savedCurveStorageKey),
              let curves = try? JSONDecoder().decode([SavedSpeedCurve].self, from: data) else { return [] }
        return curves
    }

    func saveCurve(_ target: CurveTarget, name rawName: String) {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        var list = savedCurves
        list.append(SavedSpeedCurve(name: name, curve: curve(for: target)))
        if let data = try? JSONEncoder().encode(list) {
            UserDefaults.standard.set(data, forKey: savedCurveStorageKey)
            objectWillChange.send()
            haptic(.medium)
        }
    }

    func applySavedCurve(_ saved: SavedSpeedCurve, to target: CurveTarget) {
        registerUndo()
        switch target {
        case .clip(let id):
            if let index = clips.firstIndex(where: { $0.id == id }) {
                clips[index].speedCurve = saved.curve
                clips[index].curveEnabled = true
            }
        case .global(let id):
            if let index = speedFX.firstIndex(where: { $0.id == id }) {
                speedFX[index].curve = saved.curve
                speedFX[index].name = saved.name
            }
        }
        schedulePreview()
    }

    func deleteSavedCurve(_ saved: SavedSpeedCurve) {
        var list = savedCurves
        list.removeAll { $0.id == saved.id }
        if let data = try? JSONEncoder().encode(list) {
            UserDefaults.standard.set(data, forKey: savedCurveStorageKey)
            objectWillChange.send()
            haptic(.light)
        }
    }

    func addFlatSpeedFX(at time: Double? = nil) {
        registerUndo()
        let start = min(max(0, time ?? projectTime), max(0, projectDuration))
        speedFX.append(GlobalSpeedFX(name: "Speed FX", start: start, duration: 0.8, curve: .flat))
        schedulePreview()
        haptic(.selection)
    }
}
