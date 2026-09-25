from pathlib import Path
import re

p = Path('VeloCutAI/VeloCutAI/VeloCutV4.swift')
s = p.read_text()

# IMPORTANT: this patch is intentionally additive. It runs immediately after
# patch_v050_pro_workspace.py and does not replace timelineCanvas, lane geometry,
# scrolling, zoom, playhead, speed curves, clip cards, or the v0.5 audio lane.

# Add overlay-only UI state beside existing editor state.
state_pat = re.compile(r'(@State\s+private\s+var\s+multiSelectedClips\s*:\s*Set<UUID>\s*=\s*\[\])')
s, n = state_pat.subn(r'''\1
    @State private var v051AnimationCollapsed = true
    @State private var v051AnimationHeight: CGFloat = 58
    @State private var v051TrackNames: [Int:String] = [0:"V1",1:"V2",2:"V3"]
    @State private var v051BypassedTracks: Set<Int> = []
    @State private var v051TrackColors: [Int:Color] = [0:.blue,1:.purple,2:.pink]''', s, count=1)
if n != 1:
    raise RuntimeError('v0.5 editor state anchor missing')

mark = '    private var topBar:some View'
if mark not in s:
    raise RuntimeError('v0.5 topBar anchor missing')

helpers = r'''    private var v051AnimationOverlay: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    withAnimation(.snappy) { v051AnimationCollapsed.toggle() }
                } label: {
                    Image(systemName: v051AnimationCollapsed ? "chevron.right" : "chevron.down")
                }
                .buttonStyle(.plain)

                Text("Animation").font(.caption.bold())

                Button { model.haptic(.selection) } label: {
                    Image(systemName: "diamond.badge.plus")
                }
                .buttonStyle(.plain)

                Spacer()

                Button { model.haptic(.selection) } label: {
                    Image(systemName: "plus.square.on.square")
                }
                .buttonStyle(.plain)

                Button { model.haptic(.selection) } label: {
                    Image(systemName: "square.and.arrow.down")
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .frame(height: 30)
            .background(model.workspaceTheme.panel.opacity(0.92))

            if !v051AnimationCollapsed {
                GeometryReader { geo in
                    let center = geo.size.width / 2
                    ZStack {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.secondary.opacity(0.045))
                        HStack(spacing: 18) {
                            ForEach(0..<7, id: \.self) { _ in
                                Image(systemName: "diamond.fill")
                                    .font(.system(size: 7))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Rectangle()
                            .fill(Color.red.opacity(0.8))
                            .frame(width: 1.1, height: max(38, v051AnimationHeight))
                            .position(x: center, y: max(38, v051AnimationHeight) / 2)
                    }
                }
                .frame(height: max(38, v051AnimationHeight))

                Capsule()
                    .fill(Color.secondary.opacity(0.35))
                    .frame(width: 40, height: 4)
                    .frame(height: 10)
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0).onChanged { value in
                            v051AnimationHeight = min(150, max(38, v051AnimationHeight + value.translation.height))
                        }
                    )
            }
        }
    }

    private var v051TrackControlsOverlay: some View {
        HStack(spacing: 7) {
            ForEach(0..<3, id: \.self) { lane in
                HStack(spacing: 4) {
                    Menu {
                        Button("Rename") { v051TrackNames[lane] = "Track \(lane + 1)" }
                        Menu("Color") {
                            Button("Blue") { v051TrackColors[lane] = .blue }
                            Button("Purple") { v051TrackColors[lane] = .purple }
                            Button("Pink") { v051TrackColors[lane] = .pink }
                            Button("Green") { v051TrackColors[lane] = .green }
                            Button("Orange") { v051TrackColors[lane] = .orange }
                        }
                    } label: {
                        Text(v051TrackNames[lane] ?? "V\(lane + 1)")
                            .font(.system(size: 9, weight: .bold))
                            .lineLimit(1)
                            .frame(width: 34, height: 24)
                            .background(v051TrackColors[lane] ?? Color.secondary, in: RoundedRectangle(cornerRadius: 6))
                            .foregroundStyle(.white)
                    }
                    .buttonStyle(.plain)

                    Button {
                        if v051BypassedTracks.contains(lane) { v051BypassedTracks.remove(lane) }
                        else { v051BypassedTracks.insert(lane) }
                        model.haptic(.selection)
                    } label: {
                        Text("B")
                            .font(.system(size: 9, weight: .bold))
                            .frame(width: 23, height: 24)
                            .background(v051BypassedTracks.contains(lane) ? Color.orange.opacity(0.42) : Color.secondary.opacity(0.13), in: RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }
            }

            Spacer(minLength: 4)

            Menu {
                Button { model.isFileImporting = true } label: { Label("Video / Photo", systemImage: "film") }
                Button { model.isAudioImporting = true } label: { Label("Audio", systemImage: "waveform") }
                Button { model.haptic(.selection) } label: { Label("Text", systemImage: "textformat") }
                Button { model.haptic(.selection) } label: { Label("Effect", systemImage: "sparkles") }
                Button { model.haptic(.selection) } label: { Label("Transition", systemImage: "arrow.left.and.right") }
                Button { model.haptic(.selection) } label: { Label("Speed FX", systemImage: "waveform.path.ecg") }
            } label: {
                Image(systemName: "plus.circle.fill").font(.system(size: 18))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 10)
        .frame(height: 34)
        .background(model.workspaceTheme.panel.opacity(0.72))
    }

'''
s = s.replace(mark, helpers + mark, 1)

# Insert overlays in BOTH v0.5 workspace layouts without changing the timeline itself.
landscape_anchor = 'VStack(spacing:0){workspaceHandle;if let target=curveTarget'
landscape_repl = 'VStack(spacing:0){workspaceHandle;v051AnimationOverlay;v051TrackControlsOverlay;if let target=curveTarget'
if landscape_anchor not in s:
    raise RuntimeError('v0.5 landscape workspace anchor missing')
s = s.replace(landscape_anchor, landscape_repl, 1)

portrait_anchor = 'playback;workspaceHandle;if let target=curveTarget'
portrait_repl = 'playback;workspaceHandle;v051AnimationOverlay;v051TrackControlsOverlay;if let target=curveTarget'
if portrait_anchor not in s:
    raise RuntimeError('v0.5 portrait workspace anchor missing')
s = s.replace(portrait_anchor, portrait_repl, 1)

p.write_text(s)
print('Applied additive v0.5.1 overlay without replacing the v0.5 timeline engine')
