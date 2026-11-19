import Foundation
import PDFKit
import AppKit

// Builds the Oxford Reading Tree asset library:
//  - copies each PDF and matching MP3 into app/src/main/assets/oxford
//  - renders a portrait cover thumbnail for every book
//  - writes library.json
//
// Usage: swift tools/OxfordAssetBuilder.swift

let fileManager = FileManager.default
let projectRoot = URL(fileURLWithPath: fileManager.currentDirectoryPath)
let pdfRoot = URL(fileURLWithPath: "/Users/henry/Downloads/english/【PDF】牛津树1-9级")
let audioRoot = URL(fileURLWithPath: "/Users/henry/Downloads/english/【音频 美音】牛津树1-9级")
let assetsRoot = projectRoot.appendingPathComponent("app/src/main/assets/oxford")
let pdfOut = assetsRoot.appendingPathComponent("pdf")
let audioOut = assetsRoot.appendingPathComponent("audio")
let coverOut = assetsRoot.appendingPathComponent("covers")

try? fileManager.createDirectory(at: pdfOut, withIntermediateDirectories: true)
try? fileManager.createDirectory(at: audioOut, withIntermediateDirectories: true)
try? fileManager.createDirectory(at: coverOut, withIntermediateDirectories: true)

func normalizeTitle(_ raw: String) -> String {
    var name = raw
    if name.lowercased().hasSuffix(".pdf") { name = String(name.dropLast(4)) }
    // Strip the leading "1-01 " book number.
    if let range = name.range(of: #"^\d+\s*-\s*\d+\s+"#, options: .regularExpression) {
        name.removeSubrange(range)
    }
    // Remove Chinese source tags such as 【有书】 and (无字书).
    name = name.replacingOccurrences(of: #"[【（(][^】）)]*[】）)]"#, with: "", options: .regularExpression)
    name = name.replacingOccurrences(of: "_", with: " ")
    name = name.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    name = name.trimmingCharacters(in: .whitespacesAndNewlines)
    return name
}

func numberPrefix(_ name: String) -> String? {
    guard let range = name.range(of: #"^\d+\s*-\s*\d+"#, options: .regularExpression) else { return nil }
    let value = name[range].replacingOccurrences(of: " ", with: "")
    let parts = value.split(separator: "-")
    guard parts.count == 2, let level = Int(parts[0]), let number = Int(parts[1]) else { return nil }
    return String(format: "%d-%02d", level, number)
}

func listFiles(_ dir: URL, extensions: Set<String>) -> [URL] {
    (try? fileManager.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.fileSizeKey], options: [.skipsHiddenFiles]))?
        .filter { extensions.contains($0.pathExtension.lowercased()) }
        .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
        ?? []
}

func drawCover(from pdfURL: URL, to outURL: URL, width: Int, height: Int) -> Bool {
    guard let document = PDFDocument(url: pdfURL), let page = document.page(at: 0) else { return false }
    let bounds = page.bounds(for: .mediaBox)
    guard bounds.width > 0, bounds.height > 0 else { return false }

    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else { return false }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    if let context = NSGraphicsContext.current?.cgContext {
        context.setFillColor(NSColor(calibratedRed: 0.973, green: 0.949, blue: 0.894, alpha: 1).cgColor)
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        let inset: CGFloat = 10
        let scale = min((CGFloat(width) - inset * 2) / bounds.width,
                        (CGFloat(height) - inset * 2) / bounds.height)
        let drawWidth = bounds.width * scale
        let drawHeight = bounds.height * scale
        context.saveGState()
        context.translateBy(x: (CGFloat(width) - drawWidth) / 2,
                            y: (CGFloat(height) - drawHeight) / 2)
        context.scaleBy(x: scale, y: scale)
        page.draw(with: .mediaBox, to: context)
        context.restoreGState()
    }
    NSGraphicsContext.restoreGraphicsState()

    guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.82]) else {
        return false
    }
    do {
        try data.write(to: outURL)
        return true
    } catch {
        return false
    }
}

struct BookRecord {
    let id: String
    let level: Int
    let number: Int
    let title: String
    let pdfAsset: String
    let audioAsset: String?
    let coverAsset: String
    let pages: Int
    let aspect: Double
}

var levels: [[String: Any]] = []
var totalBooks = 0

for level in 1...9 {
    let pdfDir = pdfRoot.appendingPathComponent("【牛津树 PDF】Level (\(level))")
    let audioDir = audioRoot.appendingPathComponent("【美音】Level (\(level))")
    let pdfs = listFiles(pdfDir, extensions: ["pdf"])
    let audios = listFiles(audioDir, extensions: ["mp3"])
    var audioByNumber: [String: URL] = [:]
    for audio in audios {
        if let key = numberPrefix(audio.lastPathComponent) {
            if audioByNumber[key] == nil { audioByNumber[key] = audio }
        }
    }

    var records: [BookRecord] = []
    for pdf in pdfs {
        guard let key = numberPrefix(pdf.lastPathComponent),
              let number = Int(key.split(separator: "-").last ?? "") else { continue }
        guard let document = PDFDocument(url: pdf), document.pageCount > 0 else { continue }
        let firstPage = document.page(at: 0)
        let bounds = firstPage?.bounds(for: .mediaBox) ?? CGRect(x: 0, y: 0, width: 3, height: 4)
        let aspect = bounds.height > 0 ? Double(bounds.width / bounds.height) : 0.75

        let id = String(format: "L%d-%03d", level, number)
        let title = normalizeTitle(pdf.lastPathComponent)
        let pdfName = "\(id).pdf"
        let coverName = "\(id).jpg"
        let targetPDF = pdfOut.appendingPathComponent(pdfName)
        let targetCover = coverOut.appendingPathComponent(coverName)

        if !fileManager.fileExists(atPath: targetPDF.path) {
            do { try fileManager.copyItem(at: pdf, to: targetPDF) }
            catch { print("copy pdf failed \(pdf.path): \(error)"); continue }
        }

        var audioAsset: String? = nil
        if let audio = audioByNumber[key] {
            let audioName = "\(id).\(audio.pathExtension.lowercased())"
            let targetAudio = audioOut.appendingPathComponent(audioName)
            if !fileManager.fileExists(atPath: targetAudio.path) {
                do { try fileManager.copyItem(at: audio, to: targetAudio) }
                catch { print("copy audio failed \(audio.path): \(error)") }
            }
            if fileManager.fileExists(atPath: targetAudio.path) {
                audioAsset = "oxford/audio/\(audioName)"
            }
        }

        if !fileManager.fileExists(atPath: targetCover.path) {
            let coverWidth = 420
            let coverHeight = max(240, min(720, Int(420.0 / max(0.35, aspect))))
            _ = drawCover(from: pdf, to: targetCover, width: coverWidth, height: coverHeight)
        }

        records.append(BookRecord(
            id: id,
            level: level,
            number: number,
            title: title,
            pdfAsset: "oxford/pdf/\(pdfName)",
            audioAsset: audioAsset,
            coverAsset: "oxford/covers/\(coverName)",
            pages: document.pageCount,
            aspect: aspect
        ))
    }

    records.sort { $0.number < $1.number }
    var books: [[String: Any]] = []
    for record in records {
        var book: [String: Any] = [
            "id": record.id,
            "number": record.number,
            "title": record.title,
            "pdf": record.pdfAsset,
            "cover": record.coverAsset,
            "pages": record.pages,
            "aspect": record.aspect
        ]
        if let audio = record.audioAsset { book["audio"] = audio }
        books.append(book)
    }
    totalBooks += books.count
    levels.append([
        "level": level,
        "name": "Level \(level)",
        "nameCn": "第 \(level) 级",
        "books": books
    ])
    print("Level \(level): \(books.count) books")
}

let library: [String: Any] = [
    "title": "Oxford Reading Tree",
    "titleCn": "牛津树分级绘本",
    "levels": levels
]
let jsonData = try JSONSerialization.data(withJSONObject: library, options: [.prettyPrinted, .sortedKeys])
try jsonData.write(to: assetsRoot.appendingPathComponent("library.json"))
print("Wrote library.json with \(totalBooks) books")
