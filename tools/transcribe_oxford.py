#!/usr/bin/env python3
"""Transcribe the Oxford audiobooks with whisper.cpp.

The transcript is used to fill pages that have no printed text (the original
"wordless" books) and pages where OCR found only a label. It is not used to
replace good printed-text OCR.
"""
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PROJECT, 'app/src/main/assets')
OUT = '/tmp/oxford_whisper'
MODEL = '/tmp/ggml-base.en.bin'
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(ASSETS, 'oxford/library.json'), encoding='utf-8') as f:
    library = json.load(f)
books = []
for level in library['levels']:
    for book in level['books']:
        books.append(book)
print('books:', len(books))


def transcribe(book):
    book_id = book['id']
    out_base = os.path.join(OUT, book_id)
    out_json = out_base + '.json'
    if os.path.exists(out_json) and os.path.getsize(out_json) > 100:
        return book_id, 'cached'
    audio = os.path.join(ASSETS, book['audio'])
    wav = os.path.join(OUT, book_id + '.wav')
    if not os.path.exists(audio):
        return book_id, 'missing audio'
    try:
        subprocess.run([
            'afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1',
            audio, wav
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([
            'whisper-cli', '-m', MODEL, '-f', wav, '-oj', '-of', out_base
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return book_id, 'failed: ' + str(e)
    finally:
        if os.path.exists(wav):
            os.remove(wav)
    return book_id, 'ok'


done = 0
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(transcribe, b) for b in books]
    for future in as_completed(futures):
        book_id, status = future.result()
        done += 1
        if status != 'ok' and status != 'cached':
            print(book_id, status)
        if done % 10 == 0:
            print('progress', done, '/', len(books))
            sys.stdout.flush()
print('transcription complete')
