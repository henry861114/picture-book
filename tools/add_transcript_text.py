#!/usr/bin/env python3
"""Fill wordless/weak-OCR pages with the audiobook transcript.

For pages that already have good printed-text OCR, the OCR is kept. Pages with
no text (the original wordless books) or only a short label use the Whisper
transcript, aligned by the page start/end times.
"""
import glob
import json
import os
import re

ASSETS = 'app/src/main/assets/oxford'
TEXT_ROOT = os.path.join(ASSETS, 'text')
WHISPER_ROOT = '/tmp/oxford_whisper'

META = [
    'stage ', 'kipper stories', 'more stories', 'first sentences', 'first words',
    'this story is called', 'written by', 'illustrated by',
    'when you hear this sound', 'turn the page', 'now open the book',
    "let's look at the pictures", 'lets look at the pictures',
    "let's read the story", 'lets read the story', 'let us read the story',
    'what do you think', 'can you find', 'look at the pictures',
    'oxford reading tree', 'biff, chip and kipper', 'read the story together',
]


def is_meta(text):
    low = text.lower()
    return any(m in low for m in META)


def split_sentences(text):
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    matches = list(re.finditer(r'[^.!?]+[.!?]+["”’]?', text))
    out = []
    for m in matches:
        s = m.group(0).strip()
        if s:
            out.append(s)
    if matches:
        tail_start = matches[-1].end()
        tail = text[tail_start:].strip()
        if tail:
            out.append(tail)
    else:
        out.append(text)
    return out


def clean_transcript(text):
    text = text.replace('Pricta', 'Brychta').replace('Brikta', 'Brychta')
    text = text.replace('Rodra Kunt', 'Roderick Hunt')
    text = text.replace('Rodrik Hunt', 'Roderick Hunt')
    text = text.replace('Rodrick Hunt', 'Roderick Hunt')
    text = text.replace(' Mom ', ' Mum ')
    text = re.sub(r'\s+', ' ', text).strip()
    if text and text[-1] not in '.!?"”’':
        text += '.'
    return text


def load_segments(book_id):
    path = os.path.join(WHISPER_ROOT, book_id + '.json')
    if not os.path.exists(path):
        return []
    data = json.load(open(path, encoding='utf-8'))
    segments = []
    for seg in data.get('transcription', []):
        text = clean_transcript(seg.get('text', '').strip())
        if not text or is_meta(text):
            continue
        offsets = seg.get('offsets', {})
        start = int(offsets.get('from', 0))
        end = int(offsets.get('to', start + 1000))
        segments.append((start, end, text))
    return segments


def weak_page(sentences):
    if not sentences:
        return True
    text = ' '.join(s.get('en', '') for s in sentences).strip()
    words = re.findall(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", text)
    if len(words) <= 2:
        return True
    if len(words) <= 5 and not re.search(r'[.!?]', text):
        return True
    return False


def main():
    files = sorted(glob.glob(os.path.join(TEXT_ROOT, '*.json')))
    filled_pages = 0
    for path in files:
        book_id = os.path.splitext(os.path.basename(path))[0]
        data = json.load(open(path, encoding='utf-8'))
        pages = data['pages']
        segments = load_segments(book_id)
        for page in pages:
            start = page.get('startMs', 0)
            end = page.get('endMs', 0)
            if not weak_page(page.get('sentences', [])):
                continue
            page_segments = []
            for sstart, send, text in segments:
                mid = (sstart + send) / 2
                if end > start and start <= mid < end:
                    page_segments.append((sstart, text))
            if not page_segments:
                continue
            text = ' '.join(t for _, t in sorted(page_segments))
            sentences = split_sentences(text)
            if not sentences:
                continue
            page['sentences'] = [{'en': s} for s in sentences]
            filled_pages += 1
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print('filled pages:', filled_pages)


if __name__ == '__main__':
    main()
