#!/usr/bin/env python3
"""Translate Level 5 sentences with MyMemory, keeping character names intact.

Names are replaced with their Chinese forms before translation, so the service
does not turn "Kipper" into "小鹦鹉" or leave "Chip" as "小菲".
"""
import glob
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = 'app/src/main/assets/oxford/text'
CACHE = '/tmp/l5_translations.json'
EMAIL = 'picturebook@example.com'

NAME_MAP = [
    # multi-word phrases first
    ('Mrs May', '梅老师'),
    ('Mr Johnson', '约翰逊先生'),
    ('Sleeping Beauty', '睡美人'),
    ('The Magic Key', '魔法钥匙'),
    ('Magic Key', '魔法钥匙'),
    # characters
    ('Biff', '比夫'),
    ('Chip', '奇普'),
    ('Kipper', '基珀'),
    ('Wilf', '威尔夫'),
    ('Wilma', '威尔玛'),
    ('Floppy', '弗洛皮'),
    ('Nadim', '纳迪姆'),
    ('Anneena', '安妮娜'),
    ('Gran', '奶奶'),
    ('Mum', '妈妈'),
    ('Dad', '爸爸'),
    ('Jo', '乔'),
    ('Jones', '琼斯'),
    ('Arthur', '亚瑟'),
    ('Noah', '诺亚'),
    ('Fred', '弗雷德'),
    ('Blot', '布洛特'),
    ('Baron', '男爵'),
    ('Wizard', '巫师'),
    ('King', '国王'),
    ('Ark', '方舟'),
    ('Welsh', '威尔士'),
    ('Trolls', '巨魔'),
]


def protect_names(text):
    for src, dst in NAME_MAP:
        text = re.sub(r'\b' + re.escape(src) + r'\b', dst, text)
    return text


def restore_names(text):
    # Safety net for common mistranslations.
    replacements = {
        '小菲': '奇普', '小 चिप': '奇普', '小 Chip': '奇普',
        '小 Biff': '比夫', '小鹦鹉': '基珀', '腌鱼': '基珀',
        '软盘': '弗洛皮', '奇普的': '奇普的',
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


def translate(q):
    params = {
        'q': q,
        'langpair': 'en|zh-CN',
        'de': EMAIL,
    }
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    status = data.get('responseStatus')
    if status != 200:
        raise RuntimeError(f'status {status}: {data.get("responseDetails")}')
    if data.get('quotaFinished'):
        raise RuntimeError('quota finished')
    return html.unescape(data.get('responseData', {}).get('translatedText', ''))


def main():
    texts = []
    seen = set()
    for path in sorted(glob.glob(os.path.join(ROOT, 'L5-*.json'))):
        d = json.load(open(path, encoding='utf-8'))
        for page in d['pages']:
            for s in page['sentences']:
                en = s['en'].strip()
                if en and en not in seen:
                    seen.add(en)
                    texts.append(en)
    print('unique L5 sentences:', len(texts))

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding='utf-8'))
    print('cached:', len(cache))

    batches = []
    current = []
    current_len = 0
    for text in texts:
        if text in cache:
            continue
        protected = protect_names(text)
        if current and current_len + len(protected) + 1 > 430:
            batches.append(current)
            current = []
            current_len = 0
        current.append((text, protected))
        current_len += len(protected) + 1
    if current:
        batches.append(current)

    print('batches:', len(batches))
    for index, batch in enumerate(batches, 1):
        q = '\n'.join(p for _, p in batch)
        try:
            translated = translate(q)
            lines = [x.strip() for x in translated.splitlines() if x.strip()]
            if len(lines) != len(batch):
                raise RuntimeError(f'line mismatch {len(lines)} != {len(batch)}')
            for (original, _), line in zip(batch, lines):
                cache[original] = restore_names(line)
        except Exception as e:
            print('batch failed:', index, e)
            # Try one sentence at a time so one bad request does not lose the batch.
            for original, protected in batch:
                try:
                    line = translate(protected).strip()
                    cache[original] = restore_names(line)
                except Exception as inner:
                    print('sentence failed:', original[:50], inner)
                time.sleep(0.3)
        if index % 10 == 0:
            print('progress', index, '/', len(batches), 'cache', len(cache))
            json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            time.sleep(0.5)
        time.sleep(0.7)

    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('translations:', len(cache))

    # Apply to Level 5 text.
    changed = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'L5-*.json'))):
        d = json.load(open(path, encoding='utf-8'))
        for page in d['pages']:
            for s in page['sentences']:
                zh = cache.get(s['en'].strip())
                if zh:
                    s['zh'] = zh
                    changed += 1
        json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('sentences updated:', changed)


if __name__ == '__main__':
    main()
