import SwiftUI

struct AudioTimelineClipV51: View {
    let name: String
    let width: CGFloat
    let height: CGFloat
    let collapsed: Bool
    let onToggleCollapse: () -> Void
    let onMove: (CGFloat) -> Void

    var body: some View {
        HStack(spacing: 6) {
            Button(action: onToggleCollapse) {
                Image(systemName: collapsed ? "chevron.right" : "chevron.down")
                    .font(.system(size: 9, weight: .bold))
                    .frame(width: 18, height: 18)
            }
            .buttonStyle(.plain)

            Text("A1")
                .font(.system(size: 9, weight: .bold))

            if !collapsed {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        HStack(spacing: 2) {
                            ForEach(0..<max(8, Int(geo.size.width / 5)), id: \.self) { i in
                                let phase = CGFloat((i * 37) % 13) / 12.0
                                Capsule()
                                    .fill(Color.accentColor.opacity(0.78))
                                    .frame(width: 2, height: max(5, geo.size.height * (0.18 + phase * 0.62)))
                            }
                        }
                        .frame(maxHeight: .infinity)

                        Text(name)
                            .font(.system(size: 9, weight: .medium))
                            .lineLimit(1)
                            .padding(.horizontal, 5)
                            .background(.ultraThinMaterial, in: Capsule())
                            .padding(.leading, 3)
                    }
                }
            } else {
                Text(name)
                    .font(.system(size: 9, weight: .medium))
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 5)
        .frame(width: max(54, width), height: height)
        .background(Color.accentColor.opacity(0.13), in: RoundedRectangle(cornerRadius: 7))
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(Color.accentColor.opacity(0.55), lineWidth: 1))
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 4)
                .onEnded { onMove($0.translation.width) }
        )
    }
}
