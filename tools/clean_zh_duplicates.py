#!/usr/bin/env python3
"""Clean duplicated attribution translations in the Chinese text.

Merged dialogue+attribution sentences ended up like
'"Biff说。Biff说道。' — the attribution got translated twice.
When the English ends with an attribution clause and the Chinese carries
two short 说/道 clauses, the redundant trailing one is dropped.
"""
import glob
import json
import os
import re
import sys

ROOT = 'app/src/main/assets/oxford/text'
LEVELS = sys.argv[1:] or ['5', '6']

ATTRIB_EN = re.compile(r'\b(Said|Asked|Called|Shouted|Cried|Laughed|Whispered|'
                       r'Replied|Answered|Groaned|Moaned|Yelled|Wailed|Sniffed)\b'
                       r'[A-Za-z ]*\.\s*$', re.I)


def fix_zh(zh):
    if not zh:
        return zh
    parts = [p for p in re.split(r'(?<=[。！？!?])', zh) if p.strip()]
    if len(parts) < 2:
        return zh
    say_idx = [i for i, p in enumerate(parts)
               if ('说' in p or '道' in p) and len(p.strip('“”" 。')) <= 10]
    if len(say_idx) >= 2:
        last = say_idx[-1]
        if last == len(parts) - 1:
            zh = ''.join(parts[:last]).strip()
    return zh


def main():
    changed = 0
    for level in LEVELS:
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            data = json.load(open(path, encoding='utf-8'))
            touched = False
            for page in data['pages']:
                for s in page.get('sentences', []):
                    if ATTRIB_EN.search(s.get('en', '').strip()):
                        new = fix_zh(s.get('zh', ''))
                        if new != s.get('zh', ''):
                            s['zh'] = new
                            changed += 1
                            touched = True
            if touched:
                json.dump(data, open(path, 'w', encoding='utf-8'),
                          ensure_ascii=False, indent=2)
    print('zh duplicates cleaned:', changed)


if __name__ == '__main__':
    main()
