#!/usr/bin/env python3
"""Deduplicate repeated text in the reader data (all levels).

- Adjacent sentences where the next one just repeats the previous
  sentence's attribution ("... she said." / "She said.") are dropped and
  the first sentence's window extended.
- An immediate quoted-fragment repeat inside a sentence ("Come back!"
  "Come back!") is collapsed; legitimate word-play repeats ("lots and
  lots", "smaller and smaller") are kept.
- Attribution clauses with an article ("said the pirate. Said the
  pirate.") are collapsed too.
- Chinese fragments that immediately repeat their predecessor are dropped
  (unless the English genuinely repeats the same words).
"""
import glob
import json
import os
import re
import sys

ROOT = 'app/src/main/assets/oxford/text'
LEVELS = sys.argv[1:] or ['5', '6', '7', '8', '9']

V = r'(Said|Asked|Called|Shouted|Cried|Laughed|Whispered|Replied|Answered|' \
    r'Groaned|Moaned|Yelled|Wailed|Sniffed)'


def norm_words(text):
    text = (text or '').lower().replace('\u2019', "'")
    return [w for w in re.sub(r"[^a-z0-9' ]", ' ', text).split() if w]


def zh_key(frag):
    return re.sub(r'[“”"。，,！!？?、\s]', '', frag)


def collapse_attrib(en):
    # "..." said the pirate. Said the pirate.  →  "..." said the pirate.
    pat = re.compile(
        r'^(.*\b' + V + r' (?:the |a |an |his |her |their )?\w+[.!?]["”’]?)\s*'
        r'' + V + r'\b.*$', re.I)
    m = pat.match(en.strip())
    if m:
        return m.group(1)
    # Multi-word names: "... said Father Christmas. Said Father Christmas."
    phrase = re.compile(
        r'\b' + V + r' ((?:the |a |an |his |her |their )?'
        r"[A-Z][\w']*(?: [A-Z][\w']*)*)\.?(?=[\"”’)]|$| )", re.I)
    hits = [(mm.start(), mm.group(0).strip()) for mm in phrase.finditer(en)]
    for i in range(1, len(hits)):
        if hits[i][1].lower() == hits[i - 1][1].lower():
            return en[:hits[i][0]].rstrip()
    return en


def collapse_quoted_repeat(en):
    # "Come back!" "Come back!"  →  "Come back!"
    # Token-based: an immediate repeat of a multi-word segment that carries
    # sentence punctuation (!/?) is an echo; word-play repeats ("lots and
    # lots", "smaller and smaller") have no punctuation and stay.
    tokens = en.split()
    if len(tokens) >= 4:
        for size in range(len(tokens) // 2, 1, -1):
            for a in range(len(tokens) - 2 * size + 1):
                first = tokens[a:a + size]
                second = tokens[a + size:a + 2 * size]
                key = lambda tk: re.sub(r'["“”‘’]', '', tk)
                if [key(t) for t in first] == [key(t) for t in second]:
                    joined = ' '.join(first)
                    if re.search(r'[!?]', joined) or joined.endswith(('"', '"', '”')):
                        new_tokens = tokens[:a + size] + tokens[a + 2 * size:]
                        return ' '.join(new_tokens)
    pat = re.compile(r'("[^"]{1,50}[!?.]"?)\s*\1', re.I)
    prev = None
    while prev != en:
        prev = en
        en = pat.sub(r'\1', en)
    return en


def is_genuine_en_repeat(en):
    w = norm_words(en)
    for k in (2, 3):
        for a in range(len(w) - 2 * k + 1):
            if w[a:a + k] == w[a + k:a + 2 * k]:
                return True
    return False


def dedupe_zh(en, zh):
    if not zh:
        return zh
    parts = [p for p in re.split(r'(?<=[。！？!?])', zh) if p.strip()]
    if len(parts) < 2:
        return zh
    genuine = is_genuine_en_repeat(en)
    out = [parts[0]]
    for i in range(1, len(parts)):
        cur, prev = zh_key(parts[i]), zh_key(out[-1])
        if not genuine and cur and cur == prev:
            continue
        if not genuine and cur and len(cur) <= 6 and out[0] and cur == zh_key(out[0]) \
                and len(parts) > 2 and i == len(parts) - 1:
            continue
        out.append(parts[i])
    return ''.join(out)


def main():
    dropped = collapsed = zh_fixed = 0
    for level in LEVELS:
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            data = json.load(open(path, encoding='utf-8'))
            touched = False
            for page in data['pages']:
                sents = page.get('sentences', [])
                out = []
                for s in sents:
                    en = s.get('en', '').strip()
                    en2 = collapse_attrib(en)
                    en2 = collapse_quoted_repeat(en2)
                    if en2 != en:
                        s['en'] = en2
                        collapsed += 1
                        touched = True
                    zh2 = dedupe_zh(s['en'], s.get('zh', ''))
                    if zh2 != s.get('zh', ''):
                        s['zh'] = zh2
                        zh_fixed += 1
                        touched = True
                    out.append(s)
                # Adjacent tail-duplicates: drop the echo sentence.
                final = []
                for s in out:
                    if final:
                        w_prev = norm_words(final[-1].get('en', ''))
                        w_cur = norm_words(s.get('en', ''))
                        if w_cur and 0 < len(w_cur) <= 14 \
                                and w_prev[-len(w_cur):] == w_cur:
                            final[-1]['endMs'] = max(final[-1]['endMs'],
                                                     s.get('endMs', 0))
                            dropped += 1
                            touched = True
                            continue
                    final.append(s)
                page['sentences'] = final
            if touched:
                json.dump(data, open(path, 'w', encoding='utf-8'),
                          ensure_ascii=False, indent=2)
    print(f'collapsed: {collapsed}, zh fixed: {zh_fixed}, echoes dropped: {dropped}')


if __name__ == '__main__':
    main()
