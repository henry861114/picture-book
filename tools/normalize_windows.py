#!/usr/bin/env python3
"""Normalize sentence/page audio windows for the given levels.

Guarantees that the reader's position-based paging works:
- sentence windows are monotonically increasing and never overlap;
- a window never has endMs <= startMs; too-short windows get a duration
  estimated from the word count;
- page windows derive from their sentences and never overlap the previous
  page; pages without sentences become 1 ms flip-through windows.
"""
import glob
import json
import os
import re
import sys

ASSETS = 'app/src/main/assets/oxford'
LEVELS = sys.argv[1:] or ['5', '6']


def words_of(text):
    return len(re.findall(r"[A-Za-z0-9']+", text or ''))


def main():
    for level in LEVELS:
        for path in sorted(glob.glob(os.path.join(ASSETS, 'text', f'L{level}-*.json'))):
            data = json.load(open(path, encoding='utf-8'))
            prev_end = 0
            prev_page_end = 0
            for page in data['pages']:
                sents = page.get('sentences', [])
                if not sents:
                    page['startMs'] = prev_page_end
                    page['endMs'] = prev_page_end + 1
                    prev_page_end = page['endMs']
                    continue
                for s in sents:
                    start = s.get('startMs', -1)
                    end = s.get('endMs', -1)
                    if start < 0:
                        start = prev_end
                    if end <= start:
                        end = start + max(200, int(words_of(s.get('en', '')) * 330) + 400)
                    if start < prev_end:
                        # Overlap with the previous sentence: keep order.
                        start = prev_end
                        if end < start + 200:
                            end = start + 200
                    s['startMs'] = start
                    s['endMs'] = end
                    prev_end = end
                page_start = max(0, sents[0]['startMs'] - 150)
                page_start = max(page_start, prev_page_end)
                page_end = max(sents[-1]['endMs'] + 350, page_start + 1)
                page['startMs'] = page_start
                page['endMs'] = page_end
                prev_page_end = page_end
            json.dump(data, open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
    print('normalized L' + ','.join(LEVELS))


if __name__ == '__main__':
    main()
