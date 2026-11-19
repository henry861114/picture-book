#!/usr/bin/env python3
"""Sync /tmp/intro_trim.json with the retrimmed text data.

For every book, find where the first story sentence begins in the
(untrimmed) word transcript and record that as the trim start, so that
audit_text_audio.py maps app times onto the transcript correctly.
"""
import glob
import json
import os
import re

TEXT_ROOT = 'app/src/main/assets/oxford/text'
WORD_ROOT = '/tmp/oxford_words_all'
TP = '/tmp/intro_trim.json'


def norm(text):
    text = (text or '').lower().replace('\u2019', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def main():
    trim = json.load(open(TP, encoding='utf-8')) if os.path.exists(TP) else {}
    updated = 0
    for path in sorted(glob.glob(os.path.join(TEXT_ROOT, 'L*.json'))):
        book_id = os.path.splitext(os.path.basename(path))[0]
        word_path = os.path.join(WORD_ROOT, book_id + '.json')
        if not os.path.exists(word_path):
            continue
        data = json.load(open(path, encoding='utf-8'))
        first_page = next((p for p in data['pages'] if p.get('sentences')), None)
        if not first_page:
            continue
        targets = [norm(t) for s in first_page['sentences'][:2]
                   for t in re.findall(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z0-9]+)*",
                                       s.get('en', ''))][:6]
        if not targets:
            continue
        words = json.load(open(word_path, encoding='utf-8'))
        tokens = [(norm(seg.get('text', '')), int(seg['offsets']['from']))
                  for seg in words.get('transcription', [])]
        tokens = [(w, a) for w, a in tokens if w]
        # Find a run of consecutive words matching the sentence head,
        # tolerating a couple of Whisper mis-hearings.
        start = None
        need = max(2, int(len(targets) * 0.7))
        for i in range(len(tokens) - len(targets) + 1):
            hits = sum(1 for k in range(len(targets))
                       if tokens[i + k][0] == targets[k])
            if hits >= need:
                start = tokens[i][1]
                break
        if start is None:
            continue
        old = int(trim.get(book_id, {}).get('start', -1))
        if old != start:
            trim[book_id] = {'start': start,
                             'duration': trim.get(book_id, {}).get('duration', 0)}
            updated += 1
    json.dump(trim, open(TP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('intro_trim entries:', len(trim), 'updated:', updated)


if __name__ == '__main__':
    main()
