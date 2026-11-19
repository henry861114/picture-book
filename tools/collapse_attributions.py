#!/usr/bin/env python3
"""Collapse duplicated attribution clauses in the English sentences.

Transcript fragments like '"...," said Biff.' followed by 'Said Biff.'
merged into '"...," said Biff. Said Biff.'; the redundant trailing
attribution is removed.
"""
import glob
import json
import os
import re
import sys

ROOT = 'app/src/main/assets/oxford/text'
LEVELS = sys.argv[1:] or ['5', '6']
V = r'(Said|Asked|Called|Shouted|Cried|Laughed|Whispered|Replied|Answered|' \
    r'Groaned|Moaned|Yelled|Wailed|Sniffed)'
# Attribution with a name ("said Mr Johnson." / "Said Biff.") possibly
# followed by a repeated one.
PAT = re.compile(r'^(.*\b' + V + r' \w+(?: \w+)?\.)\s*' + V + r'\b.*$', re.I)
# Pronoun attribution echo: '...he said. He said.'
PATP = re.compile(r'^(.*\b(?:He|She|They|It|We)\s+' + V + r'\.)\s*'
                  r'(?:He|She|They|It|We)\s+' + V + r'\..*$', re.I)


def collapse(en):
    m = PAT.match(en)
    if m:
        return m.group(1)
    m = PATP.match(en)
    if m:
        return m.group(1)
    return en


def main():
    count = 0
    for level in LEVELS:
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            data = json.load(open(path, encoding='utf-8'))
            touched = False
            for page in data['pages']:
                for s in page.get('sentences', []):
                    en = s.get('en', '').strip()
                    fixed = collapse(en)
                    if fixed != en:
                        s['en'] = fixed
                        count += 1
                        touched = True
            if touched:
                json.dump(data, open(path, 'w', encoding='utf-8'),
                          ensure_ascii=False, indent=2)
    print('collapsed:', count)


if __name__ == '__main__':
    main()
