#!/usr/bin/env python3
"""Make sure every story page shows some text.

Illustration-only pages in the original books have no printed text. For a
read-along app it is more useful to show the nearest story sentence than an
empty panel, so those pages borrow the closest non-empty page's text. Covers
and pure back-matter pages are left alone.
"""
import glob
import json
import os
import re

ROOT = 'app/src/main/assets/oxford/text'
BACK = [
    'play a game', 'find the word', 'talk together', 'this story practises',
    'book band', 'isbn', 'available in packs', 'teaching notes',
    'word recognition', 'language comprehension', 'read the story',
]


def is_empty(page):
    return not page.get('sentences')


def is_back(page):
    text = ' '.join(s.get('en', '') for s in page.get('sentences', [])).lower()
    return any(k in text for k in BACK)


def main():
    changed = 0
    for path in sorted(glob.glob(os.path.join(ROOT, '*.json'))):
        data = json.load(open(path, encoding='utf-8'))
        pages = data['pages']
        sources = []
        for i, page in enumerate(pages):
            if i > 0 and not is_empty(page) and not is_back(page) and not page.get('borrowedFrom'):
                sources.append(i)
        first_story = min(sources) if sources else len(pages)
        for i, page in enumerate(pages):
            # Do not put story text on the cover/front matter.
            if i < first_story:
                if page.get('borrowedFrom'):
                    page['sentences'] = []
                    page.pop('borrowedFrom', None)
                continue
            if i == 0:
                continue
            if not is_empty(page) and not is_back(page):
                continue
            # Find the nearest good source page.
            best = None
            for s in sources:
                if best is None or abs(s - i) < abs(best - i):
                    best = s
            if best is None:
                continue
            page['sentences'] = [dict(s) for s in pages[best]['sentences']]
            page['borrowedFrom'] = best + 1
            changed += 1
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('filled/borrowed pages:', changed)


if __name__ == '__main__':
    main()
