from pathlib import Path
import re

p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# Universal audio item stored on the SAME v0.5 lanes. No new timeline/view hierarchy.
anchor='struct EditorClip: Identifiable, Equatable {'
if anchor not in s: raise RuntimeError('EditorClip anchor missing')
audio_struct='''struct TimelineAudioClip: Identifiable, Equatable {
    let id: UUID
    let url: URL
    var name: String
    var duration: Double
    var start: Double
    var track: Int
    var volume: Double
    init(id: UUID = UUID(), url: URL, name: String, duration: Double, start: Double, track: Int, volume: Double = 1) {
        self.id=id; self.url=url; self.name=name; self.duration=duration; self.start=start; self.track=track; self.volume=volume
    }
    var end: Double { start + duration }
}

struct PickedStillImage: Transferable {
    let data: Data
    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(importedContentType: .image) { PickedStillImage(data: $0) }
    }
}

'''
s=s.replace(anchor,audio_struct+anchor,1)

# View-model state lives beside existing music state.
state='@Published var musicURL: URL?'
if state not in s: raise RuntimeError('music state missing')
s=s.replace(state,'@Published var audioClips: [TimelineAudioClip] = []\n    @Published var bypassedTracks: Set<Int> = []\n    '+state,1)

# Import video to a specific existing v0.5 lane. Existing callers keep lane 0.
s=s.replace('func importVideos(_ urls: [URL]) {','func importVideos(_ urls: [URL], toTrack targetTrack: Int? = nil) {',1)
s=s.replace('newClips.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: d, trimStart: 0, trimEnd: d))','newClips.append(EditorClip(url: url, name: url.deletingPathExtension().lastPathComponent, duration: d, trimStart: 0, trimEnd: d, track: min(2,max(0,targetTrack ?? 0))))',1)

# Per-lane audio import/extraction + drag.
method_anchor='    private func localSpeed(_ clip: EditorClip, normalized: Double) -> Double {'
if method_anchor not in s: raise RuntimeError('localSpeed anchor missing')
methods='''    func importAudioClip(_ url: URL, toTrack track: Int, at time: Double? = nil) {
        Task {
            do {
                let d=max(0.05,CMTimeGetSeconds(try await asset(for:url).load(.duration)))
                audioClips.append(TimelineAudioClip(url:url,name:url.deletingPathExtension().lastPathComponent,duration:d,start:max(0,time ?? projectTime),track:min(2,max(0,track))))
                schedulePreview(immediate:true); haptic(.medium)
            } catch { errorMessage="Не удалось открыть аудио: \\(error.localizedDescription)" }
        }
    }

    func extractAudioFromVideo(_ url: URL, toTrack track: Int, at time: Double? = nil) {
        guard !isAudioExtracting else{return}; isAudioExtracting=true
        Task {
            do {
                let u=try await VeloCutAudioTools.extractAudio(from:url)
                let d=max(0.05,CMTimeGetSeconds(try await asset(for:u).load(.duration)))
                audioClips.append(TimelineAudioClip(url:u,name:url.deletingPathExtension().lastPathComponent+" • audio",duration:d,start:max(0,time ?? projectTime),track:min(2,max(0,track))))
                schedulePreview(immediate:true); haptic(.medium)
            } catch { errorMessage="Извлечение аудио: \\(error.localizedDescription)" }
            isAudioExtracting=false
        }
    }

    func moveAudioClip(_ id: UUID, translation: CGSize, pps: Double) {
        guard let i=audioClips.firstIndex(where:{$0.id==id}) else{return}
        let original=audioClips[i]
        audioClips[i].start=max(0,original.start+Double(translation.width)/max(1,pps))
        let laneDelta=Int((translation.height/52).rounded())
        audioClips[i].track=min(2,max(0,original.track+laneDelta))
        schedulePreview()
    }

    func deleteAudioClip(_ id:UUID){audioClips.removeAll{$0.id==id};schedulePreview(immediate:true)}
    func toggleTrackBypass(_ lane:Int){if bypassedTracks.contains(lane){bypassedTracks.remove(lane)}else{bypassedTracks.insert(lane)};schedulePreview(immediate:true)}

    func importStillImage(_ data: Data, toTrack track: Int) {
        Task {
            do { let u=try await makeStillVideo(data); importVideos([u],toTrack:track) }
            catch { errorMessage="Не удалось импортировать фото: \\(error.localizedDescription)" }
        }
    }

    private func makeStillVideo(_ data:Data) async throws -> URL {
        guard let cg=UIImage(data:data)?.cgImage else { throw NSError(domain:"VeloCut",code:70,userInfo:[NSLocalizedDescriptionKey:"Неверное изображение"]) }
        let w=max(2,cg.width-(cg.width%2)),h=max(2,cg.height-(cg.height%2))
        let out=FileManager.default.temporaryDirectory.appendingPathComponent("VeloCut-Still-\\(UUID().uuidString).mp4")
        try? FileManager.default.removeItem(at:out)
        let writer=try AVAssetWriter(outputURL:out,fileType:.mp4)
        let input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:w,AVVideoHeightKey:h])
        input.expectsMediaDataInRealTime=false
        let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,kCVPixelBufferWidthKey as String:w,kCVPixelBufferHeightKey as String:h])
        guard writer.canAdd(input) else{throw NSError(domain:"VeloCut",code:71,userInfo:[NSLocalizedDescriptionKey:"Photo writer"])};writer.add(input)
        guard writer.startWriting() else{throw writer.error ?? NSError(domain:"VeloCut",code:72)};writer.startSession(atSourceTime:.zero)
        var pb:CVPixelBuffer?;CVPixelBufferPoolCreatePixelBuffer(nil,adaptor.pixelBufferPool!,&pb)
        guard let pb else{throw NSError(domain:"VeloCut",code:73)}
        CVPixelBufferLockBaseAddress(pb,[]);defer{CVPixelBufferUnlockBaseAddress(pb,[])}
        guard let ctx=CGContext(data:CVPixelBufferGetBaseAddress(pb),width:w,height:h,bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(pb),space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue) else{throw NSError(domain:"VeloCut",code:74)}
        ctx.draw(cg,in:CGRect(x:0,y:0,width:w,height:h))
        while !input.isReadyForMoreMediaData { try? await Task.sleep(nanoseconds:2_000_000) }
        adaptor.append(pb,withPresentationTime:.zero);adaptor.append(pb,withPresentationTime:CMTime(seconds:3,preferredTimescale:600));input.markAsFinished()
        await withCheckedContinuation{c in writer.finishWriting{c.resume()}}
        if writer.status != .completed { throw writer.error ?? NSError(domain:"VeloCut",code:75) }
        return out
    }

'''
s=s.replace(method_anchor,methods+method_anchor,1)

# Add lane audio to preview/export mix. Keep legacy global music for inspector compatibility.
mix_anchor='let mix = AVMutableAudioMix(); mix.inputParameters = [audioParams, musicParams].compactMap { $0 }; return (composition, mix)'
if mix_anchor not in s: raise RuntimeError('mix anchor missing')
mix_repl='''var laneAudioParams:[AVMutableAudioMixInputParameters]=[]
        if includeMusic {
            for item in audioClips where !bypassedTracks.contains(item.track) {
                let a=asset(for:item.url)
                guard let src=try await a.loadTracks(withMediaType:.audio).first,
                      let dst=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid) else{continue}
                let maxD=max(0.05,min(item.duration,CMTimeGetSeconds(try await a.load(.duration))))
                let range=CMTimeRange(start:.zero,duration:CMTime(seconds:maxD,preferredTimescale:600))
                try? dst.insertTimeRange(range,of:src,at:CMTime(seconds:item.start,preferredTimescale:600))
                let ap=AVMutableAudioMixInputParameters(track:dst);ap.setVolume(Float(item.volume),at:CMTime(seconds:item.start,preferredTimescale:600));laneAudioParams.append(ap)
            }
        }
        let mix = AVMutableAudioMix(); mix.inputParameters = [audioParams, musicParams].compactMap { $0 } + laneAudioParams; return (composition, mix)'''
s=s.replace(mix_anchor,mix_repl,1)

# Bypass video clips at composition time, preserving the original composition engine otherwise.
s=s.replace('for clip in sourceClips {','for clip in sourceClips where !bypassedTracks.contains(clip.track) {',1)

# Editor state for per-track + actions.
state_anchor='@State private var expandedLanes:Set<Int>=[]'
if state_anchor not in s: raise RuntimeError('expanded lanes state missing')
s=s.replace(state_anchor,state_anchor+'''\n    @State private var trackNames:[Int:String]=[0:"V1",1:"V2",2:"V3"]
    @State private var pendingMediaLane:Int?
    @State private var pendingAudioLane:Int?
    @State private var pendingExtractLane:Int?
    @State private var showTrackMediaPicker=false
    @State private var showTrackExtractPicker=false
    @State private var trackMediaItems:[PhotosPickerItem]=[]
    @State private var trackExtractItem:PhotosPickerItem?''',1)

# Per-track audio file uses the existing AudioPicker sheet.
s=s.replace('.sheet(isPresented:$model.isAudioImporting){AudioPicker{model.isAudioImporting=false;model.importMusic($0)}}','.sheet(isPresented:$model.isAudioImporting){AudioPicker{u in model.isAudioImporting=false;if let lane=pendingAudioLane{model.importAudioClip(u,toTrack:lane,at:model.projectTime);pendingAudioLane=nil}else{model.importMusic(u)}}}',1)

# Gallery pickers launched by the + on the selected lane.
body_hook='.onChange(of:photoItems){_,items in loadPhotos(items)}'
if body_hook not in s: raise RuntimeError('photo onChange missing')
body_extra='''.photosPicker(isPresented:$showTrackMediaPicker,selection:$trackMediaItems,maxSelectionCount:20,matching:.any(of:[.videos,.images]))
        .photosPicker(isPresented:$showTrackExtractPicker,selection:$trackExtractItem,matching:.videos)
        .onChange(of:trackMediaItems){_,items in loadUniversalMedia(items)}
        .onChange(of:trackExtractItem){_,item in
            guard let item,let lane=pendingExtractLane else{return}
            Task{if let movie=try? await item.loadTransferable(type:PickedMovie.self){await model.extractAudioFromVideo(movie.url,toTrack:lane,at:model.projectTime)}else{await MainActor.run{model.errorMessage="Не удалось открыть видео"}};await MainActor.run{trackExtractItem=nil;pendingExtractLane=nil}}
        }'''
s=s.replace(body_hook,body_hook+'\n        '+body_extra,1)

# Remove ONLY the separate A1 UI introduced by v0.5. Keep workspace/nav/zoom untouched.
s=s.replace('timeline;audioLaneV50','timeline')
s=s.replace('timeline.frame(maxHeight:.infinity);audioLaneV50','timeline.frame(maxHeight:.infinity)')

# Replace only the lane header row inside original timelineCanvas. Geometry and gesture stay unchanged.
old_lane='ForEach(0..<3,id:\\.self){lane in let top=laneTop(lane);RoundedRectangle(cornerRadius:8).fill(Color.secondary.opacity(.06)).frame(height:videoH-3).offset(y:top);Button{if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}}label:{HStack(spacing:3){Text("V\\(lane+1)");Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down")}.font(.system(size:9,weight:.bold)).padding(4).background(.thinMaterial,in:Capsule())}.buttonStyle(.plain).position(x:24,y:top+12);if expandedLanes.contains(lane){RoundedRectangle(cornerRadius:7).fill(Color.accentColor.opacity(.035)).frame(height:curveH-2).offset(y:top+videoH);Text("Speed").font(.system(size:8,weight:.semibold)).foregroundStyle(.secondary).position(x:22,y:top+videoH+10)}}'
if old_lane not in s: raise RuntimeError('original v0.5 lane block missing')
new_lane='''ForEach(0..<3,id:\\.self){lane in
                let top=laneTop(lane)
                RoundedRectangle(cornerRadius:8).fill(Color.secondary.opacity(.06)).frame(height:videoH-3).offset(y:top)
                Menu{
                    Button("Переименовать"){trackNames[lane]="Track \\(lane+1)"}
                    Button("Удалить содержимое",role:.destructive){for c in model.clips.filter({$0.track==lane}){model.deleteClip(c.id)};for a in model.audioClips.filter({$0.track==lane}){model.deleteAudioClip(a.id)}}
                }label:{Text(trackNames[lane] ?? "V\\(lane+1)").font(.system(size:9,weight:.bold)).lineLimit(1).frame(width:38,height:28).background(Color.accentColor.opacity(.22),in:RoundedRectangle(cornerRadius:7))}.buttonStyle(.plain).position(x:24,y:top+videoH/2)
                Button{model.toggleTrackBypass(lane)}label:{Text("B").font(.system(size:9,weight:.bold)).frame(width:23,height:25).background(model.bypassedTracks.contains(lane) ? Color.orange.opacity(.42):Color.secondary.opacity(.13),in:RoundedRectangle(cornerRadius:6))}.buttonStyle(.plain).position(x:58,y:top+videoH/2)
                Menu{
                    Button{pendingMediaLane=lane;showTrackMediaPicker=true}label:{Label("Видео / Фото",systemImage:"photo.on.rectangle")}
                    Button{pendingAudioLane=lane;model.isAudioImporting=true}label:{Label("Аудиофайл",systemImage:"waveform.badge.plus")}
                    Button{pendingExtractLane=lane;showTrackExtractPicker=true}label:{Label("Извлечь аудио из видео",systemImage:"video.badge.waveform")}
                    Button{inspector = .text}label:{Label("Текст",systemImage:"textformat")}
                    Button{inspector = .filters}label:{Label("FX / Фильтр",systemImage:"sparkles")}
                    Button{inspector = .speed}label:{Label("Speed FX",systemImage:"waveform.path.ecg.rectangle")}
                }label:{Image(systemName:"plus.circle.fill").font(.system(size:18)).frame(width:30,height:30)}.buttonStyle(.plain).position(x:geo.size.width-18,y:top+videoH/2)
                Button{if expandedLanes.contains(lane){expandedLanes.remove(lane)}else{expandedLanes.insert(lane)}}label:{Image(systemName:expandedLanes.contains(lane) ? "chevron.up":"chevron.down").font(.system(size:8,weight:.bold)).frame(width:20,height:20).background(.thinMaterial,in:Circle())}.buttonStyle(.plain).position(x:84,y:top+videoH/2)
                if expandedLanes.contains(lane){RoundedRectangle(cornerRadius:7).fill(Color.accentColor.opacity(.035)).frame(height:curveH-2).offset(y:top+videoH);Text("Speed").font(.system(size:8,weight:.semibold)).foregroundStyle(.secondary).position(x:22,y:top+videoH+10)}
            }'''
s=s.replace(old_lane,new_lane,1)

# Draw audio inside those same lanes before video cards. No new row.
video_cards='            ForEach(Array(model.layouts.enumerated()),id:\\.element.id){index,l in'
if video_cards not in s: raise RuntimeError('video cards anchor missing')
audio_cards='''            ForEach(model.audioClips){a in
                let w=max(54,a.duration*pps),x=center+(a.start-model.projectTime)*pps+w/2,top=laneTop(a.track)
                HStack(spacing:4){Image(systemName:"waveform").font(.system(size:9));Text(a.name).font(.system(size:8,weight:.semibold)).lineLimit(1)}.padding(.horizontal,7).frame(width:w,height:38).background(Color.cyan.opacity(model.bypassedTracks.contains(a.track) ? 0.08:0.22),in:RoundedRectangle(cornerRadius:8)).overlay(RoundedRectangle(cornerRadius:8).stroke(Color.cyan.opacity(0.55),lineWidth:1)).position(x:x,y:top+videoH/2).highPriorityGesture(LongPressGesture(minimumDuration:0.28).sequenced(before:DragGesture(minimumDistance:0)).onEnded{v in if case .second(true,let d?)=v{if hypot(d.translation.width,d.translation.height)<8{model.deleteAudioClip(a.id)}else{model.moveAudioClip(a.id,translation:d.translation,pps:pps)}}})
            }
'''
s=s.replace(video_cards,audio_cards+video_cards,1)

# Media loader for lane +. Videos retain native pipeline; photos become 3-second still clips.
loader_anchor='    private func loadPhotos(_ items:[PhotosPickerItem])'
if loader_anchor not in s: raise RuntimeError('loadPhotos anchor missing')
loader='''    private func loadUniversalMedia(_ items:[PhotosPickerItem]){
        guard !items.isEmpty,let lane=pendingMediaLane else{return}
        Task{
            var videos:[URL]=[];var images:[Data]=[]
            for item in items{
                if let m=try? await item.loadTransferable(type:PickedMovie.self){videos.append(m.url)}
                else if let img=try? await item.loadTransferable(type:PickedStillImage.self){images.append(img.data)}
            }
            await MainActor.run{if !videos.isEmpty{model.importVideos(videos,toTrack:lane)};for d in images{model.importStillImage(d,toTrack:lane)};trackMediaItems=[];pendingMediaLane=nil}
        }
    }

'''
s=s.replace(loader_anchor,loader+loader_anchor,1)

p.write_text(s)
print('Applied universal items directly to original v0.5 tracks; navigation/zoom/timeline gesture unchanged')
