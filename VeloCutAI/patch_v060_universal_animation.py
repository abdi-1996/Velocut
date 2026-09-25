from pathlib import Path
import re
p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift');s=p.read_text()
state='@Published var audioDuration = 0.0'
if state not in s: raise RuntimeError('v052 state missing')
s=s.replace(state,state+'\n    let universalTimeline = UniversalTimelineStore()',1)
s=s.replace('VStack(spacing:0){workspaceHandle;if let target=curveTarget','VStack(spacing:0){workspaceHandle;animationTimelineV6;if let target=curveTarget',1)
s=s.replace('preview.frame(height:max(150,root.size.height*model.previewSplit));playback;workspaceHandle\n                if let target=curveTarget','preview.frame(height:max(150,root.size.height*model.previewSplit));playback;workspaceHandle;animationTimelineV6\n                if let target=curveTarget',1)
mark='    private var timeline:some View'
if mark not in s: raise RuntimeError('timeline property missing')
ui=r'''    private var animationTimelineV6:some View{
        VStack(spacing:0){
            HStack(spacing:7){Button{withAnimation(.snappy){model.universalTimeline.animationCollapsed.toggle()}}label:{Image(systemName:model.universalTimeline.animationCollapsed ? "chevron.right":"chevron.down")};Text("Animation").font(.caption.bold());Button{model.universalTimeline.addAnimation(at:model.projectTime)}label:{Image(systemName:"plus.diamond.fill")};Spacer();if let id=model.universalTimeline.selectedAnimationClipID{Button{model.universalTimeline.duplicateAnimation(id)}label:{Image(systemName:"plus.square.on.square")}}}.padding(.horizontal,10).frame(height:30).background(.thinMaterial)
            if !model.universalTimeline.animationCollapsed{GeometryReader{geo in let pps=34.0*model.timelineZoom,center=geo.size.width/2;ZStack(alignment:.topLeading){Rectangle().fill(Color.secondary.opacity(0.045));ForEach(model.universalTimeline.animationClips){clip in let w=max(48,CGFloat(clip.duration*pps));let x=center+CGFloat((clip.start-model.projectTime)*pps)+w/2;HStack(spacing:5){Image(systemName:"diamond.fill").font(.system(size:7));Text(clip.name).font(.caption2);Spacer()}.padding(.horizontal,7).frame(width:w,height:30).background(model.universalTimeline.selectedAnimationClipID==clip.id ? Color.accentColor.opacity(0.28):Color.secondary.opacity(0.14),in:RoundedRectangle(cornerRadius:7)).position(x:x,y:24).onTapGesture{model.universalTimeline.selectedAnimationClipID=clip.id}.contextMenu{Button("Duplicate"){model.universalTimeline.duplicateAnimation(clip.id)};Button("Save preset"){} }.gesture(DragGesture().onChanged{v in if let i=model.universalTimeline.animationClips.firstIndex(where:{$0.id==clip.id}){model.universalTimeline.animationClips[i].start=max(0,clip.start+Double(v.translation.width)/pps)}})};Rectangle().fill(Color.red.opacity(0.85)).frame(width:1.2,height:max(50,model.universalTimeline.animationHeight)).position(x:center,y:max(50,model.universalTimeline.animationHeight)/2)}}.frame(height:max(50,model.universalTimeline.animationHeight));Capsule().fill(Color.secondary.opacity(0.35)).frame(width:38,height:4).frame(height:10).gesture(DragGesture().onChanged{v in model.universalTimeline.animationHeight=min(220,max(50,model.universalTimeline.animationHeight+Double(v.translation.height)))})}
        }
    }

    private var universalTrackStripV6:some View{
        VStack(spacing:3){ForEach(model.universalTimeline.tracks){track in HStack(spacing:5){Menu{Button("Rename"){model.universalTimeline.renameTrack(track.id,"Track \(track.order+1)")};Menu("Color"){ForEach(model.universalTimeline.palette,id:\.self){hex in Button(hex){model.universalTimeline.setColor(track.id,hex)}}};Button("Add below"){_ = model.universalTimeline.addTrack(after:track.id)};Button("Delete",role:.destructive){model.universalTimeline.removeTrack(track.id)}}label:{Text(track.name).font(.system(size:9,weight:.bold)).lineLimit(1).frame(width:48,height:32).background(Color(vHex:track.colorHex),in:RoundedRectangle(cornerRadius:7)).foregroundStyle(.white)}.simultaneousGesture(LongPressGesture(minimumDuration:0.35).sequenced(before:DragGesture()).onEnded{v in if case .second(true,let drag?)=v{model.universalTimeline.moveTrack(track.id,by:drag.translation.height>12 ? 1:(drag.translation.height < -12 ? -1:0))}});Button{model.universalTimeline.toggleBypass(track.id)}label:{Text("B").font(.caption.bold()).frame(width:28,height:30).background(track.bypassed ? Color.orange.opacity(0.35):Color.secondary.opacity(0.1),in:RoundedRectangle(cornerRadius:6))};Spacer();Menu{ForEach(UniversalItemKind.allCases){kind in Button{model.universalTimeline.addItem(kind,to:track.id,at:model.projectTime)}label:{Label(kind.rawValue.capitalized,systemImage:kind.symbol)}}}label:{Image(systemName:"plus.circle.fill").font(.title3)}}.padding(.horizontal,8).opacity(track.bypassed ? 0.48:1)};Button{_ = model.universalTimeline.addTrack()}label:{Label("Add track",systemImage:"plus").font(.caption)}}
    }

'''
s=s.replace(mark,ui+mark,1)
s=s.replace('VStack(spacing:4){\n            ScrollView(.vertical,showsIndicators:false)','VStack(spacing:4){\n            universalTrackStripV6\n            ScrollView(.vertical,showsIndicators:false)',1)
needle='audioDuration = max(0.05, CMTimeGetSeconds(d))'
s=s.replace(needle,needle+'\n                _ = universalTimeline.newAudioTrack(at: audioTimelineStart, name: musicName ?? "Audio", duration: audioDuration)',1)
p.write_text(s);print('Applied universal tracks + collapsible animation timeline')
