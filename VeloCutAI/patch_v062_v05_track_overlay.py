from pathlib import Path
import re
p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

state_pat=re.compile(r'(@State private var multiSelectedClips\s*:\s*Set<UUID>\s*=\s*\[\])')
s,n=state_pat.subn(r'''\1
    @State private var extraTrackCount=0
    @State private var trackNames:[Int:String]=[0:"V1",1:"V2",2:"V3",3:"Audio"]
    @State private var trackColors:[Int:Color]=[0:.blue,1:.purple,2:.pink,3:.cyan]
    @State private var bypassedTracks:Set<Int>=[]
    @State private var animationCollapsed=true
    @State private var animationHeight:CGFloat=72''',s,count=1)
if n!=1: raise RuntimeError('v0.5 timeline state missing')

mark='    private var timeline:some View'
helpers='''    private var visibleTrackCount:Int { max(3 + extraTrackCount, model.musicURL == nil ? 3 : 4) }

    private var animationTimelineV62:some View{
        VStack(spacing:0){
            HStack(spacing:7){
                Button{withAnimation(.snappy){animationCollapsed.toggle()}}label:{Image(systemName:animationCollapsed ? "chevron.right":"chevron.down")}
                Text("Animation").font(.caption.bold())
                Button{model.haptic(.selection)}label:{Image(systemName:"diamond.badge.plus")}
                Spacer()
                Button{model.haptic(.selection)}label:{Image(systemName:"plus.square.on.square")}
                Button{model.haptic(.selection)}label:{Image(systemName:"square.and.arrow.down")}
            }.padding(.horizontal,12).frame(height:30).background(.thinMaterial)
            if !animationCollapsed {
                GeometryReader{g in let center=g.size.width/2;ZStack{RoundedRectangle(cornerRadius:7).fill(Color.secondary.opacity(0.045));HStack(spacing:18){ForEach(0..<7,id:\\.self){_ in Image(systemName:"diamond.fill").font(.system(size:7)).foregroundStyle(.secondary)}};Rectangle().fill(Color.red.opacity(0.8)).frame(width:1.1,height:max(38,animationHeight)).position(x:center,y:max(38,animationHeight)/2)}}.frame(height:max(38,animationHeight))
                Capsule().fill(Color.secondary.opacity(0.35)).frame(width:40,height:4).frame(height:10).gesture(DragGesture().onChanged{v in animationHeight=min(180,max(38,animationHeight+v.translation.height))})
            }
        }
    }

'''
if mark not in s: raise RuntimeError('timeline property missing')
s=s.replace(mark,helpers+mark,1)

stack_pat=re.compile(r'''VStack\(spacing:4\)\{\s*ScrollView\(\.vertical,showsIndicators:false\)\{GeometryReader\{geo in timelineCanvas\(geo\)\}\.frame\(height:timelineRequiredHeight\)\}\.frame\(minHeight:180,maxHeight:360\)\s*audioLaneV50\s*\}''',re.S)
s,n=stack_pat.subn('''VStack(spacing:4){animationTimelineV62;ScrollView(.vertical,showsIndicators:false){GeometryReader{geo in timelineCanvas(geo)}.frame(height:timelineRequiredHeight)}.frame(minHeight:180,maxHeight:380)}''',s,count=1)
if n!=1: raise RuntimeError('v052 timeline stack missing')

s,n=re.subn(r'ForEach\(0\.\.<3\s*,\s*id:\s*\\\.self\)\s*\{\s*lane in',r'ForEach(0..<visibleTrackCount,id:\.self){lane in',s,count=1)
if n!=1: raise RuntimeError('lane range missing')

s=s.replace('Text("V\\(lane+1)")','Text(trackNames[lane] ?? "Track \\(lane+1)").lineLimit(1)',1)

anchor='.buttonStyle(.plain)\n                .position(x:24,y:top+12)'
controls='''.buttonStyle(.plain)
                .position(x:28,y:top+12)

                Button{if bypassedTracks.contains(lane){bypassedTracks.remove(lane)}else{bypassedTracks.insert(lane)}}label:{Text("B").font(.system(size:9,weight:.bold)).frame(width:24,height:24).background(bypassedTracks.contains(lane) ? Color.orange.opacity(0.38):Color.secondary.opacity(0.13),in:RoundedRectangle(cornerRadius:6))}.buttonStyle(.plain).position(x:67,y:top+12)

                Menu{
                    Button{model.isFileImporting=true}label:{Label("Video / Photo",systemImage:"film")}
                    Button{model.isAudioImporting=true}label:{Label("Audio",systemImage:"waveform")}
                    Button{model.haptic(.selection)}label:{Label("Text",systemImage:"textformat")}
                    Button{model.haptic(.selection)}label:{Label("Effect",systemImage:"sparkles")}
                    Button{model.haptic(.selection)}label:{Label("Transition",systemImage:"arrow.left.and.right")}
                    Button{extraTrackCount += 1;laneHeights[visibleTrackCount]=46;trackNames[visibleTrackCount]="Track \\(visibleTrackCount+1)"}label:{Label("Add track",systemImage:"rectangle.stack.badge.plus")}
                }label:{Image(systemName:"plus.circle.fill").font(.system(size:18))}.buttonStyle(.plain).position(x:geo.size.width-17,y:top+12)'''
if anchor in s: s=s.replace(anchor,controls,1)
else: print('warning: lane controls anchor not found; preserving original header')

audio_anchor='LaneHeightHandleV4(height:h){laneHeights[lane]=$0}'
audio='''if lane == 3, let name=model.musicName, model.musicURL != nil {
                    let duration=max(0.1,model.audioDuration),w=max(54,CGFloat(duration*pps)),x=center+CGFloat((model.audioTimelineStart-model.projectTime)*pps)+w/2
                    HStack(spacing:5){Image(systemName:"waveform").font(.caption2);Text(name).font(.system(size:8,weight:.semibold)).lineLimit(1)}
                        .padding(.horizontal,7).frame(width:w,height:max(26,h-8))
                        .background(Color.cyan.opacity(bypassedTracks.contains(lane) ? 0.08:0.2),in:RoundedRectangle(cornerRadius:7))
                        .overlay(RoundedRectangle(cornerRadius:7).stroke(Color.cyan.opacity(0.55),lineWidth:1)).position(x:x,y:top+h/2)
                        .gesture(DragGesture(minimumDistance:2).onChanged{v in model.audioTimelineStart=max(0,model.audioTimelineStart+Double(v.translation.width)/pps)}.onEnded{_ in model.schedulePreview()})
                }

                LaneHeightHandleV4(height:h){laneHeights[lane]=$0}'''
if audio_anchor in s: s=s.replace(audio_anchor,audio,1)
else: print('warning: audio insertion anchor not found')

menu_anchor='.position(x:28,y:top+12)'
menu_suffix='''.position(x:28,y:top+12)
                .contextMenu{
                    Button("Rename"){trackNames[lane]="Track \\(lane+1)"}
                    Button("Blue"){trackColors[lane] = .blue};Button("Purple"){trackColors[lane] = .purple};Button("Green"){trackColors[lane] = .green};Button("Orange"){trackColors[lane] = .orange}
                    if lane >= 3 && extraTrackCount>0 { Button("Delete track",role:.destructive){extraTrackCount -= 1} }
                }'''
if menu_anchor in s: s=s.replace(menu_anchor,menu_suffix,1)

height_pat=re.compile(r'''    private var timelineRequiredHeight:CGFloat \{.*?\n    \}''',re.S)
height_repl='''    private var timelineRequiredHeight:CGFloat {
        let scale=CGFloat(model.trackHeightScale)
        let base:CGFloat = 22 + max(30,42*scale) + 12
        let rows=(0..<visibleTrackCount).reduce(CGFloat.zero){sum,lane in sum + (model.collapsedTracks.contains(lane) ? 28 : max(32,(laneHeights[lane] ?? 46)*scale))}
        let expandedCount=(0..<visibleTrackCount).filter{expandedLanes.contains($0) && !model.collapsedTracks.contains($0)}.count
        return max(230,base+rows+CGFloat(expandedCount)*max(34,56*scale))
    }'''
s,n=height_pat.subn(height_repl,s,count=1)
if n!=1: raise RuntimeError('required height missing')

p.write_text(s)
print('Layered new controls on original v0.5 timeline; removed separate A1')
