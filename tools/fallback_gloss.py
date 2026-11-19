#!/usr/bin/env python3
"""Reuse the previous Chinese translations when the online service is unavailable."""
import difflib
import glob
import json
import os
import re
import sys

ROOT = 'app/src/main/assets/oxford/text'


def norm(text):
    text = (text or '').lower().replace('’', "'").replace('‘', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def load_backup_maps(levels):
    maps = {lv: {} for lv in levels}
    sources = ['/tmp/text_before_rebuild3', '/tmp/text_before_rebuild2', '/tmp/text_before_rebuild']
    for src in sources:
        if not os.path.isdir(src):
            continue
        for path in glob.glob(os.path.join(src, '*.json')):
            base = os.path.splitext(os.path.basename(path))[0]
            level = base.split('-')[0][1:]
            if level not in maps:
                continue
            d = json.load(open(path, encoding='utf-8'))
            for page in d['pages']:
                for s in page.get('sentences', []):
                    en = s.get('en', '').strip()
                    zh = s.get('zh', '').strip()
                    if en and zh:
                        maps[level].setdefault(en, zh)
    return maps


def main():
    levels = sys.argv[1:] or ['5', '6']
    maps = load_backup_maps(levels)
    filled = 0
    for level in levels:
        backup = maps.get(level, {})
        if not backup:
            print('no backup for L' + level)
            continue
        backup_norm = [(norm(en), en, zh) for en, zh in backup.items()]
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            d = json.load(open(path, encoding='utf-8'))
            for page in d['pages']:
                for s in page['sentences']:
                    if s.get('zh'):
                        continue
                    en = s['en'].strip()
                    words = norm(en)
                    if not words:
                        continue
                    best = None
                    for bn, ben, bzh in backup_norm:
                        sim = difflib.SequenceMatcher(None, words, bn).ratio()
                        if best is None or sim > best[0]:
                            best = (sim, ben, bzh)
                    if best and best[0] >= 0.55:
                        s['zh'] = best[2]
                        filled += 1
            json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('filled from backup:', filled)


if __name__ == '__main__':
    main()
