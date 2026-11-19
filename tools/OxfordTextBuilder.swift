import Foundation
import PDFKit
import Vision
import CoreGraphics
import AppKit

// OCRs every page of the Oxford library and writes:
//   app/src/main/assets/oxford/text/<book-id>.json
//   /tmp/oxford_words.json
//
// Each page contains the recognized English sentences. Chinese translations
// are added by the separate dictionary/translation pass.

let fileManager = FileManager.default
let projectRoot = URL(fileURLWithPath: fileManager.currentDirectoryPath)
let appAssetsRoot = projectRoot.appendingPathComponent("app/src/main/assets")
let assetsRoot = appAssetsRoot.appendingPathComponent("oxford")
let textRoot = assetsRoot.appendingPathComponent("text")
try? fileManager.createDirectory(at: textRoot, withIntermediateDirectories: true)

guard let libraryData = try? Data(contentsOf: assetsRoot.appendingPathComponent("library.json")),
      let libraryObject = try? JSONSerialization.jsonObject(with: libraryData) as? [String: Any],
      let levels = libraryObject["levels"] as? [[String: Any]] else {
    print("Cannot read library.json")
    exit(1)
}

struct BookJob {
    let id: String
    let pdfPath: String
    let pages: Int
}

var jobs: [BookJob] = []
for level in levels {
    guard let books = level["books"] as? [[String: Any]] else { continue }
    for book in books {
        if let id = book["id"] as? String,
           let pdf = book["pdf"] as? String,
           let pages = book["pages"] as? Int {
            jobs.append(BookJob(id: id, pdfPath: pdf, pages: pages))
        }
    }
}
print("OCR jobs: \(jobs.count) books")

let queue = OperationQueue()
queue.maxConcurrentOperationCount = 4
let wordsLock = NSLock()
var wordCounts: [String: Int] = [:]
var processed = 0

let knownJunk = [
    "oxford reading tree", "series created by", "illustrated by",
    "roderick hunt", "alex brychta", "first sentences", "stage 1",
    "stage 2", "stage 3", "stage 4", "stage 5", "stage 6", "stage 7",
    "stage 8", "stage 9", "oup", "oxford university press"
]

func isJunk(_ line: String) -> Bool {
    let lower = line.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
    if lower.isEmpty { return true }
    if knownJunk.contains(where: { lower == $0 || lower.hasPrefix($0 + " ") }) { return true }
    if lower.range(of: #"^\d+$"#, options: .regularExpression) != nil { return true }
    if lower.range(of: #"^[ivxlcdm]+$"#, options: [.regularExpression, .caseInsensitive]) != nil { return true }
    if lower.range(of: #"^[^a-zA-Z]*$"#, options: .regularExpression) != nil { return true }
    // Lines with only one letter plus punctuation are usually signs or OCR noise.
    let letters = lower.filter { $0.isLetter }
    if letters.count < 2 && lower != "i" && lower != "a" { return true }
    return false
}

func splitSentences(_ text: String) -> [String] {
    let cleaned = text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !cleaned.isEmpty else { return [] }
    let pattern = #"[^.!?]+[.!?]+[\"'’”]?"#
    if let regex = try? NSRegularExpression(pattern: pattern) {
        let ns = cleaned as NSString
        let matches = regex.matches(in: cleaned, range: NSRange(location: 0, length: ns.length))
        var sentences: [String] = []
        for match in matches {
            let sentence = ns.substring(with: match.range)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !sentence.isEmpty { sentences.append(sentence) }
        }
        if !sentences.isEmpty {
            // Add any trailing text without final punctuation.
            if let last = matches.last {
                let tailStart = last.range.location + last.range.length
                if tailStart < ns.length {
                    let tail = ns.substring(from: tailStart)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if !tail.isEmpty { sentences.append(tail) }
                }
            }
            return sentences
        }
    }
    return [cleaned]
}

func words(in text: String) -> [String] {
    guard let regex = try? NSRegularExpression(pattern: #"[A-Za-z]+(?:['’\-][A-Za-z]+)*"#) else { return [] }
    let ns = text as NSString
    return regex.matches(in: text, range: NSRange(location: 0, length: ns.length)).map {
        ns.substring(with: $0.range).lowercased()
    }
}

func ocrPage(document: PDFDocument, index: Int) -> [String] {
    guard let page = document.page(at: index) else { return [] }
    let bounds = page.bounds(for: .mediaBox)
    guard bounds.width > 0, bounds.height > 0 else { return [] }
    let targetWidth: CGFloat = 1500
    let scale = targetWidth / bounds.width
    let width = Int(targetWidth)
    let height = max(1, Int(bounds.height * scale))
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    guard let context = CGContext(data: nil, width: width, height: height,
                                  bitsPerComponent: 8, bytesPerRow: 0,
                                  space: colorSpace,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return []
    }
    context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: context)
    guard let image = context.makeImage() else { return [] }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return []
    }
    let observations = (request.results ?? []).sorted {
        if abs($0.boundingBox.maxY - $1.boundingBox.maxY) > 0.02 {
            return $0.boundingBox.maxY > $1.boundingBox.maxY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    var lines: [String] = []
    for observation in observations {
        guard let candidate = observation.topCandidates(1).first else { continue }
        if candidate.confidence < 0.55 { continue }
        let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if isJunk(text) { continue }
        lines.append(text)
    }
    return lines
}

for job in jobs {
    queue.addOperation {
        let pdfURL = appAssetsRoot.appendingPathComponent(job.pdfPath)
        guard let document = PDFDocument(url: pdfURL) else {
            print("Cannot open \(job.id)")
            return
        }
        var pages: [[String: Any]] = []
        var bookWords: [String: Int] = [:]
        for index in 0..<min(job.pages, document.pageCount) {
            let lines = ocrPage(document: document, index: index)
            let joined = lines.joined(separator: " ")
            let sentences = splitSentences(joined)
            var sentenceObjects: [[String: Any]] = []
            for sentence in sentences {
                sentenceObjects.append(["en": sentence])
                for word in words(in: sentence) {
                    bookWords[word, default: 0] += 1
                }
            }
            pages.append(["sentences": sentenceObjects])
        }
        let output: [String: Any] = ["id": job.id, "pages": pages]
        if let data = try? JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: textRoot.appendingPathComponent("\(job.id).json"))
        }
        wordsLock.lock()
        for (word, count) in bookWords {
            wordCounts[word, default: 0] += count
        }
        processed += 1
        let current = processed
        wordsLock.unlock()
        if current % 10 == 0 {
            print("OCR progress: \(current)/\(jobs.count)")
            fflush(stdout)
        }
    }
}

queue.waitUntilAllOperationsAreFinished()

if let data = try? JSONSerialization.data(withJSONObject: wordCounts, options: [.prettyPrinted, .sortedKeys]) {
    try? data.write(to: URL(fileURLWithPath: "/tmp/oxford_words.json"))
}
print("OCR complete. Unique words: \(wordCounts.count)")
