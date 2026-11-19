#!/usr/bin/env python3
"""Word-level Whisper (medium.en) transcripts for the given levels."""
import glob
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PROJECT, 'app/src/main/assets/oxford')
OUT = os.environ.get('OUT_ROOT', '/tmp/oxford_words_medium')
MODEL = os.environ.get('MEDIUM_MODEL', '/tmp/ggml-medium.en.bin')
LEVELS = sys.argv[1:] or ['5', '6']
os.makedirs(OUT, exist_ok=True)


def work(path):
    book_id = os.path.splitext(os.path.basename(path))[0]
    out_json = os.path.join(OUT, book_id + '.json')
    if os.path.exists(out_json) and os.path.getsize(out_json) > 100:
        return book_id, 'cached'
    audio = os.path.join(PROJECT, 'audio_m4a_untrimmed', book_id + '.m4a')
    if not os.path.exists(audio):
        audio = os.path.join(ASSETS, 'audio', book_id + '.m4a')
    wav = os.path.join(OUT, book_id + '.wav')
    try:
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1',
                        audio, wav], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['whisper-cli', '-m', MODEL, '-f', wav,
                        '-ml', '1', '-sow', '-oj', '-ojf',
                        '-of', os.path.join(OUT, book_id)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return book_id, 'failed: ' + str(e)
    finally:
        if os.path.exists(wav):
            os.remove(wav)
    return book_id, 'ok'


def main():
    files = []
    for lv in LEVELS:
        files += sorted(glob.glob(os.path.join(ASSETS, 'text', f'L{lv}-*.json')))
    print('books:', len(files), flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(work, p) for p in files]
        for i, f in enumerate(futures, 1):
            book_id, status = f.result()
            if status == 'ok':
                ok += 1
            elif status != 'cached':
                print(book_id, status, flush=True)
            if i % 5 == 0:
                print(f'{i}/{len(files)} done (ok={ok})', flush=True)
    print('finished', ok, 'of', len(files))


if __name__ == '__main__':
    main()
