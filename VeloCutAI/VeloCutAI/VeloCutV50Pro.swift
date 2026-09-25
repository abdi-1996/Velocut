import SwiftUI
import AVFoundation

enum VeloCutTheme: String, CaseIterable, Identifiable {
    case iosGlass = "iOS Glass", capcut = "Cut Dark", davinci = "Resolve", afterEffects = "Motion Pro", veloDark = "Velo Dark", veloLight = "Velo Light"
    var id:String{rawValue}
    var background:Color {
        switch self {
        case .iosGlass:return Color(uiColor:.systemGroupedBackground)
        case .capcut:return Color(white:0.055)
        case .davinci:return Color(white:0.105)
        case .afterEffects:return Color(red:0.10,green:0.10,blue:0.14)
        case .veloDark:return Color(white:0.075)
        case .veloLight:return Color(white:0.95)
        }
    }
    var panel:Color {
        switch self {
        case .iosGlass:return Color(uiColor:.secondarySystemGroupedBackground)
        case .capcut:return Color(white:0.11)
        case .davinci:return Color(white:0.16)
        case .afterEffects:return Color(red:0.16,green:0.16,blue:0.21)
        case .veloDark:return Color(white:0.13)
        case .veloLight:return .white
        }
    }
}

enum VeloCutAudioEffect:String,CaseIterable,Identifiable {
    case none="Clean",bass="Bass Boost",muffled="Muffled",phone="Phone",hall="Hall",deep="Deep",nightcore="Nightcore",slowReverb="Slow + Reverb",echo="Echo",distortion="Distortion"
    var id:String{rawValue}
}

enum VeloCutCache {
    static var root:URL {
        let fm=FileManager.default
        let base=fm.urls(for:.cachesDirectory,in:.userDomainMask).first!.appendingPathComponent("VeloCut",isDirectory:true)
        try? fm.createDirectory(at:base,withIntermediateDirectories:true)
        for n in ["Thumbnails","Waveforms","Preview","RIFE","AudioFX"]{try? fm.createDirectory(at:base.appendingPathComponent(n),withIntermediateDirectories:true)}
        return base
    }
    static func clear(){let u=root;try? FileManager.default.removeItem(at:u);_ = root}
    static func sizeBytes()->Int64 {
        let fm=FileManager.default;guard let e=fm.enumerator(at:root,includingPropertiesForKeys:[.fileSizeKey]) else{return 0};var n:Int64=0
        for case let u as URL in e{n += Int64((try? u.resourceValues(forKeys:[.fileSizeKey]).fileSize) ?? 0)};return n
    }
}

enum VeloCutAudioFX {
    static func processedURL(for source:URL,effect:VeloCutAudioEffect,pitch:Double) async throws -> URL {
        guard effect != .none || abs(pitch) > 0.5 else{return source}
        let stamp=String(source.path.hashValue.magnitude)+"-"+effect.rawValue.replacingOccurrences(of:" ",with:"_")+"-"+String(Int(pitch.rounded()))
        let out=VeloCutCache.root.appendingPathComponent("AudioFX",isDirectory:true).appendingPathComponent(stamp+".caf")
        if FileManager.default.fileExists(atPath:out.path){return out}
        return try await Task.detached(priority:.userInitiated){try render(source:source,to:out,effect:effect,pitch:pitch)}.value
    }

    private static func render(source:URL,to outputURL:URL,effect:VeloCutAudioEffect,pitch:Double) throws -> URL {
        let input=try AVAudioFile(forReading:source)
        let format=input.processingFormat
        let engine=AVAudioEngine();let player=AVAudioPlayerNode();engine.attach(player)
        var chain:[AVAudioNode]=[]
        func add(_ node:AVAudioNode){engine.attach(node);chain.append(node)}
        func eq(_ type:AVAudioUnitEQFilterType,_ frequency:Float,_ gain:Float=0)->AVAudioUnitEQ{let unit=AVAudioUnitEQ(numberOfBands:1);let b=unit.bands[0];b.filterType=type;b.frequency=frequency;b.gain=gain;b.bypass=false;return unit}
        switch effect {
        case .none:break
        case .bass:add(eq(.lowShelf,180,8))
        case .muffled:add(eq(.lowPass,1350))
        case .phone:add(eq(.highPass,320));add(eq(.lowPass,3400))
        case .hall:let r=AVAudioUnitReverb();r.loadFactoryPreset(.largeHall2);r.wetDryMix=48;add(r)
        case .deep:let t=AVAudioUnitTimePitch();t.pitch = -300;add(t);add(eq(.lowShelf,190,6))
        case .nightcore:let t=AVAudioUnitTimePitch();t.pitch=420;add(t)
        case .slowReverb:let t=AVAudioUnitTimePitch();t.pitch = -260;add(t);let r=AVAudioUnitReverb();r.loadFactoryPreset(.mediumHall);r.wetDryMix=42;add(r)
        case .echo:let d=AVAudioUnitDelay();d.delayTime=0.22;d.feedback=32;d.wetDryMix=38;add(d)
        case .distortion:let d=AVAudioUnitDistortion();d.loadFactoryPreset(.multiBrokenSpeaker);d.wetDryMix=45;add(d)
        }
        if abs(pitch)>0.5{let t=AVAudioUnitTimePitch();t.pitch=Float(min(2400,max(-2400,pitch)));add(t)}
        var previous:AVAudioNode=player
        for node in chain{engine.connect(previous,to:node,format:format);previous=node}
        engine.connect(previous,to:engine.mainMixerNode,format:format)
        try engine.enableManualRenderingMode(.offline,format:format,maximumFrameCount:4096)
        try? FileManager.default.removeItem(at:outputURL)
        let output=try AVAudioFile(forWriting:outputURL,settings:engine.manualRenderingFormat.settings)
        player.scheduleFile(input,at:nil)
        try engine.start();player.play()
        guard let buffer=AVAudioPCMBuffer(pcmFormat:engine.manualRenderingFormat,frameCapacity:4096) else{throw NSError(domain:"VeloCut.AudioFX",code:1)}
        while engine.manualRenderingSampleTime < input.length {
            let left=input.length-engine.manualRenderingSampleTime
            let frames=AVAudioFrameCount(min(Int64(buffer.frameCapacity),left))
            let status=try engine.renderOffline(frames,to:buffer)
            switch status {
            case .success:try output.write(from:buffer)
            case .cannotDoInCurrentContext:continue
            case .error:throw NSError(domain:"VeloCut.AudioFX",code:2,userInfo:[NSLocalizedDescriptionKey:"Не удалось обработать аудиоэффект"])
            @unknown default:continue
            }
        }
        player.stop();engine.stop();return outputURL
    }
}

struct VeloCutThemeSettingsV50:View {
    @ObservedObject var model:EditorViewModel
    @State private var cacheSize:Int64=0
    var body:some View {
        NavigationStack{Form{
            Section("Theme"){
                Picker("Interface",selection:$model.workspaceTheme){ForEach(VeloCutTheme.allCases){Text($0.rawValue).tag($0)}}
            }
            Section("Timeline"){
                HStack{Text("Track size");Slider(value:$model.trackHeightScale,in:0.65...1.8)}
                Button("Collapse all"){model.collapsedTracks=[0,1,2,10,11,12]}
                Button("Expand all"){model.collapsedTracks=[]}
            }
            Section("Cache"){
                HStack{Text("Limit");Slider(value:$model.cacheLimitGB,in:2...20,step:1);Text("\(Int(model.cacheLimitGB)) GB").font(.caption.monospacedDigit())}
                Text(String(format:"Used %.1f MB",Double(cacheSize)/1048576)).font(.caption).foregroundStyle(.secondary)
                Button("Clear cache",role:.destructive){VeloCutCache.clear();cacheSize=0}
            }
        }.navigationTitle("Appearance & Cache")}.onAppear{cacheSize=VeloCutCache.sizeBytes()}
    }
}
