#!/usr/bin/env python3
"""Align Level 5 sentences to word-level Whisper timestamps, page by page."""
import difflib
import glob
import json
import os
import re

TEXT_ROOT = 'app/src/main/assets/oxford/text'
WORD_ROOT = '/tmp/oxford_words'


def norm(text):
    text = (text or '').lower().replace('’', "'").replace('‘', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def load_words(book_id):
    path = os.path.join(WORD_ROOT, book_id + '.json')
    data = json.load(open(path, encoding='utf-8'))
    out = []
    for seg in data.get('transcription', []):
        w = norm(seg.get('text', ''))
        if not w:
            continue
        offsets = seg.get('offsets', {})
        start = int(offsets.get('from', 0))
        end = int(offsets.get('to', start + 50))
        if end <= start:
            end = start + 50
        out.append((w, start, end))
    return out


def page_relative(page):
    sentences = page.get('sentences', [])
    start = int(page.get('startMs', 0))
    end = int(page.get('endMs', 0))
    if end <= start or not sentences:
        for s in sentences:
            s['startMs'] = -1
            s['endMs'] = -1
        return
    lengths = [max(1, len(s.get('en', ''))) for s in sentences]
    total = sum(lengths)
    acc = 0
    for s, length in zip(sentences, lengths):
        s['startMs'] = int(round(start + (end - start) * acc / total))
        acc += length
        s['endMs'] = int(round(start + (end - start) * acc / total))


def main():
    aligned_pages = 0
    fallback_pages = 0
    for path in sorted(glob.glob(os.path.join(TEXT_ROOT, 'L5-*.json'))):
        book_id = os.path.splitext(os.path.basename(path))[0]
        data = json.load(open(path, encoding='utf-8'))
        words = load_words(book_id)
        if not words:
            continue
        for page in data['pages']:
            sentences = page.get('sentences', [])
            if not sentences:
                continue
            if page.get('borrowedFrom'):
                for s in sentences:
                    s['startMs'] = -1
                    s['endMs'] = -1
                continue
            page_start = int(page.get('startMs', 0))
            page_end = int(page.get('endMs', 0))
            if page_end <= page_start:
                page_relative(page)
                continue

            # Local word window around this page.
            local = [w for w in words
                     if w[2] >= page_start - 12000 and w[1] <= page_end + 12000]
            if not local:
                page_relative(page)
                fallback_pages += 1
                continue

            sent_words = []
            ranges = []
            for si, s in enumerate(sentences):
                ws = [norm(t) for t in re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*", s.get('en', ''))]
                ws = [w for w in ws if w]
                if not ws:
                    ranges.append((si, 0, 0, []))
                    continue
                start_index = len(sent_words)
                sent_words.extend(ws)
                ranges.append((si, start_index, len(sent_words), ws))

            if not sent_words:
                page_relative(page)
                continue

            matcher = difflib.SequenceMatcher(None, sent_words, [w[0] for w in local], autojunk=False)
            mapping = [-1] * len(sent_words)
            for block in matcher.get_matching_blocks():
                i, j, size = block
                for k in range(size):
                    if i + k < len(mapping):
                        mapping[i + k] = j + k

            results = []
            ok = True
            last_start = -1
            for si, start_index, end_index, ws in ranges:
                if not ws:
                    results.append((si, -1, -1))
                    continue
                mapped = [mapping[i] for i in range(start_index, end_index) if mapping[i] >= 0]
                if len(mapped) < max(1, int(len(ws) * 0.5)):
                    ok = False
                    break
                j0 = min(mapped)
                j1 = max(mapped)
                s_start = local[j0][1] - 40
                s_end = local[j1][2] + 60
                if s_end <= s_start or s_start < last_start:
                    ok = False
                    break
                last_start = s_start
                results.append((si, max(0, s_start), s_end))

            if not ok:
                page_relative(page)
                fallback_pages += 1
                continue

            for si, s_start, s_end in results:
                sentences[si]['startMs'] = s_start
                sentences[si]['endMs'] = s_end
            valid = [s for s in sentences if s.get('startMs', -1) >= 0
                     and s.get('endMs', 0) > s.get('startMs', 0)]
            if valid:
                page['startMs'] = max(0, min(s['startMs'] for s in valid) - 150)
                page['endMs'] = max(s['endMs'] for s in valid) + 350
            aligned_pages += 1

        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('aligned pages:', aligned_pages, 'fallback pages:', fallback_pages)


if __name__ == '__main__':
    main()
