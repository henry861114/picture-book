#!/usr/bin/env python3
"""Audit how well the in-app sentence text matches the original narration."""
import glob
import json
import os
import re
import sys
from difflib import SequenceMatcher

ASSETS = 'app/src/main/assets/oxford'
TEXT_ROOT = os.path.join(ASSETS, 'text')
WORD_ROOT = '/tmp/oxford_words_all'


def norm(text):
    text = (text or '').lower().replace('’', "'").replace('‘', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def load_words(book_id):
    path = os.path.join(WORD_ROOT, book_id + '.json')
    if not os.path.exists(path):
        return []
    data = json.load(open(path, encoding='utf-8'))
    out = []
    for seg in data.get('transcription', []):
        w = norm(seg.get('text', ''))
        if w:
            out.append((w, int(seg['offsets']['from']), int(seg['offsets']['to'])))
    return out


def audit(level_prefix):
    trim = {}
    tp = '/tmp/intro_trim.json'
    if os.path.exists(tp):
        trim = json.load(open(tp, encoding='utf-8'))
    summary = []
    worst = []
    for path in sorted(glob.glob(os.path.join(TEXT_ROOT, f'{level_prefix}-*.json'))):
        book_id = os.path.splitext(os.path.basename(path))[0]
        data = json.load(open(path, encoding='utf-8'))
        words = load_words(book_id)
        offset = int(trim.get(book_id, {}).get('start', 0))
        sentences = [(pi, si, s) for pi, p in enumerate(data['pages'])
                     for si, s in enumerate(p.get('sentences', []))]
        if not sentences:
            continue
        first_start = min(s['startMs'] for _, _, s in sentences if s.get('startMs', -1) >= 0)
        # Any narration before the first sentence?
        before = [w for w, a, b in words if b <= first_start + offset]
        ratios = []
        for pi, si, s in sentences:
            if s.get('startMs', -1) < 0:
                continue
            a = s['startMs'] + offset
            b = s['endMs'] + offset
            tw = [w for w, wa, wb in words if wa < b and wb > a]
            ow = [norm(x) for x in re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*", s['en'])]
            if not ow or not tw:
                continue
            ratio = SequenceMatcher(None, ow, tw).ratio()
            ratios.append(ratio)
            if ratio < 0.55 and len(ow) >= 3:
                worst.append((ratio, book_id, pi, s['en'], ' '.join(tw)))
        bad = sum(1 for r in ratios if r < 0.55)
        summary.append((book_id, len(sentences), round(sum(ratios) / max(1, len(ratios)), 2),
                        bad, len(before), first_start))
    print(f'== {level_prefix} books: {len(summary)}')
    for book_id, count, avg, bad, before, first_start in summary:
        if bad or before or avg < 0.85:
            print(f'{book_id}: sentences={count} avg={avg} bad={bad} words_before_first={before} first={first_start}')
    print(f'-- worst mismatches: {len(worst)}')
    worst.sort()
    for ratio, book_id, pi, en, tw in worst[:40]:
        print(f'{ratio:.2f} {book_id} p{pi}\n  EN: {en}\n  TW: {tw}')


if __name__ == '__main__':
    audit(sys.argv[1] if len(sys.argv) > 1 else 'L5')
