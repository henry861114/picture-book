import Foundation
import PDFKit
import Vision
import CoreGraphics
import AppKit

let args = CommandLine.arguments
guard args.count > 3 else { print("usage: OcrTest.swift <pdf> <page> <width>"); exit(1) }
let pdfURL = URL(fileURLWithPath: args[1])
let pageIndex = Int(args[2]) ?? 0
let width = Int(args[3]) ?? 1400

guard let doc = PDFDocument(url: pdfURL), let page = doc.page(at: pageIndex) else {
    print("cannot open pdf"); exit(1)
}
let bounds = page.bounds(for: .mediaBox)
let scale = CGFloat(width) / bounds.width
let height = Int(bounds.height * scale)
let colorSpace = CGColorSpaceCreateDeviceRGB()
guard let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                          bytesPerRow: 0, space: colorSpace,
                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
    print("cannot create context"); exit(1)
}
ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
ctx.scaleBy(x: scale, y: scale)
page.draw(with: .mediaBox, to: ctx)
guard let cgImage = ctx.makeImage() else { print("no image"); exit(1) }

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["en-US"]
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])
let observations = (request.results ?? []).sorted {
    if abs($0.boundingBox.maxY - $1.boundingBox.maxY) > 0.02 {
        return $0.boundingBox.maxY > $1.boundingBox.maxY
    }
    return $0.boundingBox.minX < $1.boundingBox.minX
}
for obs in observations {
    if let text = obs.topCandidates(1).first?.string {
        let b = obs.boundingBox
        print(String(format: "%.3f %.3f %.3f %.3f conf=%.2f | %@", b.minX, b.minY, b.width, b.height, obs.topCandidates(1).first?.confidence ?? 0, text))
    }
}
