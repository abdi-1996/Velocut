from pathlib import Path
import re
p=Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s=p.read_text()

# Add rename state to EditorView.
m=re.search(r'struct\s+EditorView\s*:\s*View\s*\{',s)
if not m: raise RuntimeError('EditorView missing')
insert='''\n    @State private var renameTrackIDV61: UUID? = nil
    @State private var renameTrackNameV61 = ""
'''
s=s[:m.end()]+insert+s[m.end():]

# Replace the visible timeline property only. Old helper functions may remain compiled but are no longer rendered.
needle='    private var timeline:some View{'
start=s.find(needle)
if start<0: raise RuntimeError('timeline body missing')
brace=s.find('{',start)
depth=0; end=None
for i in range(brace,len(s)):
    if s[i]=='{': depth+=1
    elif s[i]=='}':
        depth-=1
        if depth==0:
            end=i+1; break
if end is None: raise RuntimeError('timeline body unbalanced')
new=r'''    private var timeline:some View{
        VStack(spacing:0){
            HStack(spacing:10){
                Label("Timeline",systemImage:"timeline.selection").font(.caption.bold())
                Slider(value:$model.trackHeightScale,in:0.65...1.8).frame(maxWidth:130)
                Spacer()
                Button{model.timelineZoom=max(0.5,model.timelineZoom/1.18)}label:{Image(systemName:"minus.magnifyingglass")}
                Button{model.timelineZoom=min(6,model.timelineZoom*1.18)}label:{Image(systemName:"plus.magnifyingglass")}
            }.padding(.horizontal,10).frame(height:38)
            universalTimelineCanvasV61
        }
        .alert("Rename track",isPresented:Binding(get:{renameTrackIDV61 != nil},set:{if !$0{renameTrackIDV61=nil}})){
            TextField("Track name",text:$renameTrackNameV61)
            Button("Cancel",role:.cancel){renameTrackIDV61=nil}
            Button("Save"){if let id=renameTrackIDV61{model.universalTimeline.renameTrack(id,renameTrackNameV61)};renameTrackIDV61=nil}
        }
    }'''
s=s[:start]+new+s[end:]

# Insert the single universal timeline renderer before bottomBar.
mark='    private var bottomBar:'
pos=s.find(mark)
if pos<0: raise RuntimeError('bottomBar missing')
ui=r'''    private var universalTimelineCanvasV61:some View{
        ScrollView(.vertical,showsIndicators:false){
            VStack(spacing:4){
                ForEach(model.universalTimeline.tracks){track in
                    universalTrackRowV61(track)
                }
                Button{_ = model.universalTimeline.addTrack()}label:{Label("Add track",systemImage:"plus").font(.caption)}
                    .frame(height:34)
            }.padding(.vertical,4)
        }
        .frame(maxHeight:.infinity)
    }

    @ViewBuilder private func universalTrackRowV61(_ track:UniversalTrack)->some View{
        let rowH:CGFloat = track.collapsed ? 30 : max(38,52*CGFloat(model.trackHeightScale))
        HStack(spacing:5){
            Menu{
                Button("Rename"){renameTrackIDV61=track.id;renameTrackNameV61=track.name}
                Menu("Color"){ForEach(model.universalTimeline.palette,id:\.self){hex in Button{model.universalTimeline.setColor(track.id,hex)}label:{HStack{Circle().fill(Color(vHex:hex)).frame(width:12,height:12);Text(hex)}}}}
                Button("Add track below"){_ = model.universalTimeline.addTrack(after:track.id)}
                Button("Move up"){model.universalTimeline.moveTrack(track.id,by:-1)}
                Button("Move down"){model.universalTimeline.moveTrack(track.id,by:1)}
                Divider()
                Button("Delete",role:.destructive){model.universalTimeline.removeTrack(track.id)}
            }label:{
                Text(track.name).font(.system(size:9,weight:.bold)).lineLimit(2).multilineTextAlignment(.center)
                    .frame(width:48,height:rowH-4).background(Color(vHex:track.colorHex),in:RoundedRectangle(cornerRadius:7)).foregroundStyle(.white)
            }
            .simultaneousGesture(LongPressGesture(minimumDuration:0.35).sequenced(before:DragGesture()).onEnded{value in
                if case .second(true,let drag?)=value { model.universalTimeline.moveTrack(track.id,by:drag.translation.height > 14 ? 1:(drag.translation.height < -14 ? -1:0)) }
            })
            Button{model.universalTimeline.toggleBypass(track.id)}label:{Text("B").font(.caption.bold()).frame(width:28,height:min(34,rowH)).background(track.bypassed ? Color.orange.opacity(0.38):Color.secondary.opacity(0.10),in:RoundedRectangle(cornerRadius:6))}
            GeometryReader{geo in
                let pps=34.0*model.timelineZoom, center=geo.size.width/2
                ZStack(alignment:.topLeading){
                    RoundedRectangle(cornerRadius:7).fill(Color.secondary.opacity(0.045))
                    // Existing project video clips live in the first universal track.
                    if track.id == model.universalTimeline.tracks.first?.id {
                        ForEach(model.layouts){layout in
                            let w=max(32,CGFloat(layout.duration*pps));let x=center+CGFloat((layout.start-model.projectTime)*pps)+w/2
                            HStack(spacing:4){Image(systemName:"film.fill").font(.system(size:8));Text(layout.clip.name).font(.system(size:8,weight:.semibold)).lineLimit(1)}
                                .padding(.horizontal,6).frame(width:w,height:max(26,rowH-8))
                                .background(Color(vHex:track.colorHex).opacity(0.26),in:RoundedRectangle(cornerRadius:6))
                                .overlay(RoundedRectangle(cornerRadius:6).stroke(model.selectedClipID==layout.id ? Color.accentColor:Color.clear,lineWidth:2))
                                .position(x:x,y:rowH/2).onTapGesture{model.selectClip(layout.id)}
                        }
                    }
                    ForEach(model.universalTimeline.items.filter{$0.trackID==track.id}){item in
                        let w=max(30,CGFloat(item.duration*pps));let x=center+CGFloat((item.start-model.projectTime)*pps)+w/2
                        HStack(spacing:3){Image(systemName:item.kind.symbol).font(.system(size:8));Text(item.name).font(.system(size:8,weight:.medium)).lineLimit(1)}
                            .padding(.horizontal,5).frame(width:w,height:max(24,rowH-10))
                            .background(Color(vHex:track.colorHex).opacity(0.20),in:RoundedRectangle(cornerRadius:6))
                            .position(x:x,y:rowH/2)
                    }
                    Rectangle().fill(Color.accentColor).frame(width:1.2,height:rowH).position(x:center,y:rowH/2)
                }.clipped().contentShape(Rectangle())
                    .gesture(DragGesture(minimumDistance:3).onChanged{v in let dt = -Double(v.translation.width)/pps; model.seekProject(to:max(0,min(model.projectDuration,model.projectTime+dt)),exact:true)})
            }.frame(height:rowH)
            Menu{
                ForEach(UniversalItemKind.allCases){kind in Button{model.universalTimeline.addItem(kind,to:track.id,at:model.projectTime)}label:{Label(kind.rawValue.capitalized,systemImage:kind.symbol)}}
            }label:{Image(systemName:"plus.circle.fill").font(.title3).frame(width:34,height:rowH)}
        }.padding(.horizontal,6).frame(height:rowH).opacity(track.bypassed ? 0.50:1)
    }

'''
s=s[:pos]+ui+s[pos:]

# Remove the old extra A1 renderer from any remaining workspace/layout call sites.
s=s.replace(';audioLaneV50','')
s=s.replace('audioLaneV50;','')
s=s.replace('\n            audioLaneV50','')

p.write_text(s)
print('Applied v0.6.1 single universal timeline; legacy V1/V2/V3/A1 hidden')
