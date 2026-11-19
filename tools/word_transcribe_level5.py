#!/usr/bin/env python3
"""Word-level Whisper timestamps for Level 5 sentence synchronization."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PROJECT, 'app/src/main/assets')
OUT = '/tmp/oxford_words'
MODEL = '/tmp/ggml-base.en.bin'
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(ASSETS, 'oxford/library.json'), encoding='utf-8') as f:
    library = json.load(f)
books = [b for l in library['levels'] if l['level'] == 5 for b in l['books']]
print('L5 books:', len(books))


def work(book):
    book_id = book['id']
    out_base = os.path.join(OUT, book_id)
    out_json = out_base + '.json'
    if os.path.exists(out_json) and os.path.getsize(out_json) > 100:
        return book_id, 'cached'
    audio = os.path.join(ASSETS, book['audio'])
    wav = os.path.join(OUT, book_id + '.wav')
    try:
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1',
                        audio, wav], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['whisper-cli', '-m', MODEL, '-f', wav,
                        '-ml', '1', '-sow', '-oj', '-ojf',
                        '-of', out_base], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return book_id, 'failed: ' + str(e)
    finally:
        if os.path.exists(wav):
            os.remove(wav)
    return book_id, 'ok'


with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(work, b) for b in books]
    done = 0
    for future in as_completed(futures):
        book_id, status = future.result()
        done += 1
        if status not in ('ok', 'cached'):
            print(book_id, status)
        if done % 4 == 0:
            print('progress', done, '/', len(books))
            sys.stdout.flush()
print('word transcription complete')
