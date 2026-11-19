#!/usr/bin/env python3
"""Translate sentences that do not have Chinese yet (or force a full level)."""
import glob
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = 'app/src/main/assets/oxford/text'
CACHE = '/tmp/all_translations.json'
EMAIL = 'picturebook@example.com'

NAME_MAP = [
    ('Mrs May', '梅老师'), ('Mr Johnson', '约翰逊先生'),
    ('Mrs Green', '格林老师'), ('Miss Green', '格林老师'),
    ('Sleeping Beauty', '睡美人'), ('The Magic Key', '魔法钥匙'),
    ('Magic Key', '魔法钥匙'),
    ('Biff', '比夫'), ('Chip', '奇普'), ('Kipper', '基珀'),
    ('Wilf', '威尔夫'), ('Wilma', '威尔玛'), ('Floppy', '弗洛皮'),
    ('Nadim', '纳迪姆'), ('Anneena', '安妮娜'), ('Gran', '奶奶'),
    ('Mum', '妈妈'), ('Dad', '爸爸'), ('Jo', '乔'), ('Jones', '琼斯'),
    ('Arthur', '亚瑟'), ('Noah', '诺亚'), ('Fred', '弗雷德'),
    ('Blot', '布洛特'), ('Baron', '男爵'), ('Wizard', '巫师'),
    ('King', '国王'), ('Ark', '方舟'), ('Welsh', '威尔士'),
    ('Trolls', '巨魔'), ('Vicky', '薇琪'), ('Oprah', '奥普拉'),
]


def protect(text):
    for src, dst in NAME_MAP:
        text = re.sub(r'\b' + re.escape(src) + r'\b', dst, text)
    return text


def translate(q):
    params = {'q': q, 'langpair': 'en|zh-CN', 'de': EMAIL}
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    if data.get('responseStatus') != 200:
        raise RuntimeError(f"status {data.get('responseStatus')}: {data.get('responseDetails')}")
    if data.get('quotaFinished'):
        raise RuntimeError('quota finished')
    return html.unescape(data.get('responseData', {}).get('translatedText', ''))


def main():
    levels = sys.argv[1].split(',') if len(sys.argv) > 1 else ['5', '6']
    force_levels = set(sys.argv[2].split(',')) if len(sys.argv) > 2 else {'6'}
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding='utf-8'))

    targets = []
    seen = set()
    for level in levels:
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            d = json.load(open(path, encoding='utf-8'))
            for page in d['pages']:
                for s in page['sentences']:
                    en = s['en'].strip()
                    if not en or en in seen:
                        continue
                    seen.add(en)
                    if level in force_levels or not s.get('zh'):
                        targets.append(en)
    todo = [t for t in targets if t not in cache]
    print('targets', len(targets), 'todo', len(todo))

    batches = []
    current = []
    length = 0
    for text in todo:
        protected = protect(text)
        if current and length + len(protected) + 1 > 430:
            batches.append(current)
            current = []
            length = 0
        current.append((text, protected))
        length += len(protected) + 1
    if current:
        batches.append(current)
    print('batches', len(batches))

    stop = False
    for index, batch in enumerate(batches, 1):
        if stop:
            break
        q = '\n'.join(p for _, p in batch)
        try:
            lines = [x.strip() for x in translate(q).splitlines() if x.strip()]
            if len(lines) != len(batch):
                raise RuntimeError('line mismatch')
            for (original, _), line in zip(batch, lines):
                cache[original] = line
        except Exception as e:
            print('batch failed', index, e)
            if 'quota' in str(e).lower():
                stop = True
                break
            for original, protected in batch:
                try:
                    cache[original] = translate(protected).strip()
                except Exception as inner:
                    if 'quota' in str(inner).lower():
                        stop = True
                        break
                    print('sentence failed', original[:60], inner)
                time.sleep(0.3)
        if index % 10 == 0:
            print('progress', index, '/', len(batches), 'cache', len(cache))
            json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            time.sleep(0.4)
        time.sleep(0.65)

    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('translations', len(cache), 'stopped', stop)

    for level in levels:
        for path in sorted(glob.glob(os.path.join(ROOT, f'L{level}-*.json'))):
            d = json.load(open(path, encoding='utf-8'))
            for page in d['pages']:
                for s in page['sentences']:
                    en = s['en'].strip()
                    zh = cache.get(en)
                    if zh and (level in force_levels or not s.get('zh')):
                        s['zh'] = zh
            json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
