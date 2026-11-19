#!/usr/bin/env python3
"""Add per-sentence MP3 start/end times.

The page start/end times are already estimated. Within a page, sentence
timings are distributed by sentence length. Illustration pages that borrowed
text get -1 so the app uses TTS instead of the original audio.
"""
import glob
import json
import os

ROOT = 'app/src/main/assets/oxford/text'


def main():
    total = 0
    for path in sorted(glob.glob(os.path.join(ROOT, '*.json'))):
        data = json.load(open(path, encoding='utf-8'))
        for page in data['pages']:
            sentences = page.get('sentences', [])
            if not sentences:
                continue
            if page.get('borrowedFrom'):
                for s in sentences:
                    s['startMs'] = -1
                    s['endMs'] = -1
                continue
            start = int(page.get('startMs', 0))
            end = int(page.get('endMs', 0))
            if end <= start:
                for s in sentences:
                    s['startMs'] = -1
                    s['endMs'] = -1
                continue
            lengths = [max(1, len(s.get('en', ''))) for s in sentences]
            total_len = sum(lengths)
            acc = 0
            for s, length in zip(sentences, lengths):
                s['startMs'] = int(round(start + (end - start) * acc / total_len))
                acc += length
                s['endMs'] = int(round(start + (end - start) * acc / total_len))
                total += 1
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('sentence timings:', total)


if __name__ == '__main__':
    main()
