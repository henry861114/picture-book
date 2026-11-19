#!/usr/bin/env python3
"""Keep character names in English inside Chinese translations."""
import glob
import json
import os
import re

ROOT = 'app/src/main/assets/oxford/text'
DICT = 'app/src/main/assets/oxford/dictionary.json'

NAME_MAP = {
    '奇普': 'Chip', '比夫': 'Biff', '基珀': 'Kipper',
    '威尔夫': 'Wilf', '威尔玛': 'Wilma', '弗洛皮': 'Floppy',
    '纳迪姆': 'Nadim', '安妮娜': 'Anneena',
    '梅老师': 'Mrs May', '梅太太': 'Mrs May', '约翰逊先生': 'Mr Johnson',
    '格林老师': 'Miss Green', '乔': 'Jo', '琼斯': 'Jones',
    '亚瑟': 'Arthur', '诺亚': 'Noah', '弗雷德': 'Fred',
    '布洛特': 'Blot', '薇琪': 'Vicky', '奥普拉': 'Oprah',
    '奶奶': 'Gran', '小菲': 'Chip', '小 चिप': 'Chip',
    '小 Chip': 'Chip', '小 Biff': 'Biff', '小鹦鹉': 'Kipper',
}

DICT_NAMES = {
    'biff', 'chip', 'kipper', 'wilf', 'wilma', 'floppy', 'nadim',
    'anneena', 'johnson', 'gran', 'jo', 'jones', 'arthur', 'noah',
    'fred', 'blot', 'vicky', 'oprah', 'may',
}


def fix_text(text):
    for zh, en in NAME_MAP.items():
        text = text.replace(zh, en)
    # Add a space between Chinese and the English name.
    text = re.sub(r'(?<=[\u4e00-\u9fff])(?=[A-Za-z])', ' ', text)
    text = re.sub(r'(?<=[A-Za-z])(?=[\u4e00-\u9fff])', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def main():
    changed = 0
    for path in glob.glob(os.path.join(ROOT, '*.json')):
        data = json.load(open(path, encoding='utf-8'))
        for page in data['pages']:
            for s in page['sentences']:
                zh = s.get('zh', '')
                fixed = fix_text(zh)
                if fixed != zh:
                    s['zh'] = fixed
                    changed += 1
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('sentences changed:', changed)

    d = json.load(open(DICT, encoding='utf-8'))
    for key, entry in d.items():
        if key in DICT_NAMES:
            entry['z'] = '人名'
    json.dump(d, open(DICT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    print('dictionary name entries updated')


if __name__ == '__main__':
    main()
