import SwiftUI

enum UniversalItemKind: String, Codable, CaseIterable, Identifiable {
    case video, photo, audio, text, effect, transition, speedFX, animation
    var id:String{rawValue}
    var symbol:String { switch self { case .video:return "film"; case .photo:return "photo"; case .audio:return "waveform"; case .text:return "textformat"; case .effect:return "sparkles"; case .transition:return "arrow.left.and.right"; case .speedFX:return "gauge.with.dots.needle.67percent"; case .animation:return "diamond" } }
}
struct UniversalTrack: Identifiable, Codable, Equatable { var id=UUID(); var name:String; var colorHex:String="6C6C70"; var bypassed=false; var collapsed=false; var order:Int }
struct UniversalTimelineItem: Identifiable, Codable, Equatable { var id=UUID(); var trackID:UUID; var kind:UniversalItemKind; var name:String; var start:Double; var duration:Double }
enum AnimationInterpolation:String,Codable,CaseIterable,Identifiable { case linear,smooth,sharp,hold; var id:String{rawValue} }
struct AnimationKey:Identifiable,Codable,Equatable { var id=UUID(); var time:Double; var value:Double; var interpolation:AnimationInterpolation = .smooth }
struct AnimationParameterLane:Identifiable,Codable,Equatable { var id=UUID(); var name:String; var keys:[AnimationKey]=[] }
struct AnimationClipV6:Identifiable,Codable,Equatable { var id=UUID(); var name="Animation"; var start:Double=0; var duration:Double=1; var parameterLanes:[AnimationParameterLane]=[] }

@MainActor final class UniversalTimelineStore:ObservableObject {
    @Published var tracks:[UniversalTrack]=[.init(name:"Track 1",colorHex:"4F8CFF",order:0)]
    @Published var items:[UniversalTimelineItem]=[]
    @Published var animationCollapsed=false
    @Published var animationHeight:Double=126
    @Published var animationClips:[AnimationClipV6]=[]
    @Published var selectedAnimationClipID:UUID?
    let palette=["4F8CFF","B86BFF","FF6B88","32B67A","F0A43C","6E7B8B"]
    func addTrack(after id:UUID?=nil)->UUID { let t=UniversalTrack(name:"Track \(tracks.count+1)",colorHex:palette[tracks.count%palette.count],order:tracks.count); if let id,let i=tracks.firstIndex(where:{$0.id==id}){tracks.insert(t,at:i+1)}else{tracks.append(t)}; normalize(); return t.id }
    func removeTrack(_ id:UUID){guard tracks.count>1 else{return};items.removeAll{$0.trackID==id};tracks.removeAll{$0.id==id};normalize()}
    func renameTrack(_ id:UUID,_ name:String){guard !name.isEmpty,let i=tracks.firstIndex(where:{$0.id==id})else{return};tracks[i].name=name}
    func setColor(_ id:UUID,_ hex:String){if let i=tracks.firstIndex(where:{$0.id==id}){tracks[i].colorHex=hex}}
    func toggleBypass(_ id:UUID){if let i=tracks.firstIndex(where:{$0.id==id}){tracks[i].bypassed.toggle()}}
    func moveTrack(_ id:UUID,by delta:Int){guard let f=tracks.firstIndex(where:{$0.id==id})else{return};let t=max(0,min(tracks.count-1,f+delta));guard f != t else{return};let x=tracks.remove(at:f);tracks.insert(x,at:t);normalize()}
    func addItem(_ kind:UniversalItemKind,to track:UUID,at time:Double,duration:Double=2,name:String?=nil){items.append(.init(trackID:track,kind:kind,name:name ?? kind.rawValue.capitalized,start:max(0,time),duration:max(0.05,duration)))}
    func newAudioTrack(at time:Double,name:String,duration:Double)->UUID{let id=addTrack();renameTrack(id,name);addItem(.audio,to:id,at:time,duration:duration,name:name);return id}
    func addAnimation(at time:Double,duration:Double=1){let lanes=["Position X","Position Y","Scale","Rotation","Opacity"].map{AnimationParameterLane(name:$0)};let c=AnimationClipV6(start:max(0,time),duration:max(0.1,duration),parameterLanes:lanes);animationClips.append(c);selectedAnimationClipID=c.id}
    func duplicateAnimation(_ id:UUID){guard var c=animationClips.first(where:{$0.id==id})else{return};c.id=UUID();c.start += c.duration;c.name += " Copy";animationClips.append(c);selectedAnimationClipID=c.id}
    func addKey(clip id:UUID,laneID:UUID,time:Double,value:Double){guard let ci=animationClips.firstIndex(where:{$0.id==id}),let li=animationClips[ci].parameterLanes.firstIndex(where:{$0.id==laneID})else{return};animationClips[ci].parameterLanes[li].keys.append(.init(time:time,value:value))}
    private func normalize(){for i in tracks.indices{tracks[i].order=i}}
}
extension Color { init(vHex:String){let s=vHex.trimmingCharacters(in:.alphanumerics.inverted);var v:UInt64=0;Scanner(string:s).scanHexInt64(&v);self.init(red:Double((v>>16)&255)/255,green:Double((v>>8)&255)/255,blue:Double(v&255)/255)} }
