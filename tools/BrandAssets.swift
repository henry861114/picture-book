import Foundation
import AppKit

let project = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let assets = project.appendingPathComponent("app/src/main/assets")
let covers = assets.appendingPathComponent("oxford/covers")
let res = project.appendingPathComponent("app/src/main/res")

func bitmap(_ width: Int, _ height: Int, draw: (CGContext) -> Void) -> NSBitmapImageRep? {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    ) else { return nil }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    if let ctx = NSGraphicsContext.current?.cgContext {
        draw(ctx)
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

func saveJPEG(_ rep: NSBitmapImageRep, _ url: URL, quality: CGFloat) {
    if let data = rep.representation(using: .jpeg, properties: [.compressionFactor: quality]) {
        try? data.write(to: url)
    }
}

func savePNG(_ rep: NSBitmapImageRep, _ url: URL) {
    if let data = rep.representation(using: .png, properties: [:]) {
        try? data.write(to: url)
    }
}

func image(_ path: URL) -> NSImage? {
    NSImage(contentsOf: path)
}

// MARK: - App icon

let iconSize = 512
if let rep = bitmap(iconSize, iconSize, draw: { ctx in
    let rect = CGRect(x: 0, y: 0, width: iconSize, height: iconSize)
    let path = NSBezierPath(roundedRect: rect.insetBy(dx: 8, dy: 8), xRadius: 112, yRadius: 112)
    path.addClip()
    let colors = [NSColor(calibratedRed: 0.043, green: 0.29, blue: 0.25, alpha: 1).cgColor,
                  NSColor(calibratedRed: 0.13, green: 0.49, blue: 0.42, alpha: 1).cgColor]
    if let gradient = NSGradient(colors: colors.map { NSColor(cgColor: $0)! }) {
        gradient.draw(in: rect, angle: -55)
    }
    // subtle circle glow
    ctx.setFillColor(NSColor(white: 1, alpha: 0.06).cgColor)
    ctx.fillEllipse(in: CGRect(x: 40, y: 240, width: 430, height: 430))

    // open book
    let left = NSBezierPath()
    left.move(to: NSPoint(x: 256, y: 372))
    left.curve(to: NSPoint(x: 92, y: 330), controlPoint1: NSPoint(x: 190, y: 360), controlPoint2: NSPoint(x: 130, y: 340))
    left.line(to: NSPoint(x: 92, y: 168))
    left.curve(to: NSPoint(x: 256, y: 208), controlPoint1: NSPoint(x: 132, y: 178), controlPoint2: NSPoint(x: 196, y: 198))
    left.close()
    let right = NSBezierPath()
    right.move(to: NSPoint(x: 256, y: 372))
    right.curve(to: NSPoint(x: 420, y: 330), controlPoint1: NSPoint(x: 322, y: 360), controlPoint2: NSPoint(x: 382, y: 340))
    right.line(to: NSPoint(x: 420, y: 168))
    right.curve(to: NSPoint(x: 256, y: 208), controlPoint1: NSPoint(x: 380, y: 178), controlPoint2: NSPoint(x: 316, y: 198))
    right.close()

    let shadow = NSShadow()
    shadow.shadowColor = NSColor(white: 0, alpha: 0.25)
    shadow.shadowBlurRadius = 18
    shadow.shadowOffset = NSSize(width: 0, height: -10)
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    NSColor(calibratedRed: 1.0, green: 0.97, blue: 0.90, alpha: 1).setFill()
    left.fill()
    right.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSColor(calibratedRed: 0.87, green: 0.79, blue: 0.62, alpha: 1).setStroke()
    left.lineWidth = 3; right.lineWidth = 3
    left.stroke(); right.stroke()
    NSColor(calibratedRed: 0.78, green: 0.68, blue: 0.48, alpha: 1).setStroke()
    let spine = NSBezierPath()
    spine.move(to: NSPoint(x: 256, y: 372))
    spine.line(to: NSPoint(x: 256, y: 208))
    spine.lineWidth = 5
    spine.stroke()

    let text = "ABC" as NSString
    let attrs: [NSAttributedString.Key: Any] = [
        .font: NSFont(name: "Georgia-Bold", size: 64) ?? NSFont.boldSystemFont(ofSize: 64),
        .foregroundColor: NSColor(calibratedRed: 0.09, green: 0.42, blue: 0.36, alpha: 1)
    ]
    let size = text.size(withAttributes: attrs)
    text.draw(at: NSPoint(x: (CGFloat(iconSize) - size.width) / 2, y: 235), withAttributes: attrs)

    // gold star
    let star = NSBezierPath()
    let cx: CGFloat = 392, cy: CGFloat = 410
    for i in 0..<10 {
        let angle = CGFloat.pi / 2 + CGFloat(i) * CGFloat.pi / 5
        let r: CGFloat = i % 2 == 0 ? 44 : 19
        let p = NSPoint(x: cx + cos(angle) * r, y: cy + sin(angle) * r)
        if i == 0 { star.move(to: p) } else { star.line(to: p) }
    }
    star.close()
    NSColor(calibratedRed: 0.95, green: 0.77, blue: 0.36, alpha: 1).setFill()
    star.fill()
}) {
    savePNG(rep, project.appendingPathComponent("icon-512.png"))
    let sizes: [(String, Int)] = [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]
    for (name, size) in sizes {
        if let small = bitmap(size, size, draw: { ctx in
            if let cg = rep.cgImage {
                ctx.interpolationQuality = .high
                ctx.draw(cg, in: CGRect(x: 0, y: 0, width: size, height: size))
            }
        }) {
            let dir = res.appendingPathComponent("mipmap-\(name)")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            savePNG(small, dir.appendingPathComponent("ic_launcher.png"))
        }
    }
    print("icon written")
}

// MARK: - Home hero collage

let heroW = 1200, heroH = 900
if let rep = bitmap(heroW, heroH, draw: { ctx in
    let rect = CGRect(x: 0, y: 0, width: heroW, height: heroH)
    let bg = NSGradient(colors: [
        NSColor(calibratedRed: 0.97, green: 0.95, blue: 0.89, alpha: 1),
        NSColor(calibratedRed: 0.88, green: 0.94, blue: 0.89, alpha: 1)
    ])!
    bg.draw(in: rect, angle: -65)
    ctx.setFillColor(NSColor(calibratedRed: 0.10, green: 0.40, blue: 0.34, alpha: 0.10).cgColor)
    ctx.fillEllipse(in: CGRect(x: 560, y: 230, width: 780, height: 780))

    func drawCover(_ name: String, x: CGFloat, y: CGFloat, height: CGFloat, angle: CGFloat) {
        guard let ns = image(covers.appendingPathComponent(name)) else { return }
        let w = height * ns.size.width / ns.size.height
        NSGraphicsContext.saveGraphicsState()
        let transform = NSAffineTransform()
        transform.translateX(by: x + w / 2, yBy: y + height / 2)
        transform.rotate(byDegrees: angle)
        transform.translateX(by: -w / 2, yBy: -height / 2)
        transform.concat()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor(white: 0, alpha: 0.28)
        shadow.shadowBlurRadius = 24
        shadow.shadowOffset = NSSize(width: 0, height: -12)
        shadow.set()
        ns.draw(in: NSRect(x: 0, y: 0, width: w, height: height),
                from: NSRect(origin: .zero, size: ns.size),
                operation: .sourceOver, fraction: 0.98)
        NSGraphicsContext.restoreGraphicsState()
    }

    drawCover("L1-025.jpg", x: 220, y: 130, height: 610, angle: -7)
    drawCover("L5-002.jpg", x: 545, y: 90, height: 660, angle: 4)
    drawCover("L9-001.jpg", x: 760, y: 150, height: 430, angle: 9)

    // The layout adds its own dark scrim for the title text.
}) {
    saveJPEG(rep, assets.appendingPathComponent("home_hero.jpg"), quality: 0.88)
    print("hero written")
}
