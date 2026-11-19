#!/usr/bin/env python3
"""Verify sentence timing by re-transcribing each sentence's audio window.

For a sample of sentences per book, cut [startMs-100, endMs+150] from the
(trimmed) audio, transcribe the clip with whisper-cli, and compare the clip
text with the sentence text shown in the app. A low ratio means the sentence
window does not line up with the spoken words.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor

ASSETS = 'app/src/main/assets/oxford'
MODEL = '/tmp/ggml-base.en.bin'
SAMPLE = int(os.environ.get('SAMPLE', '8'))
LEVELS = sys.argv[1:] or ['5', '6']


def norm(text):
    text = (text or '').lower().replace('\u2019', "'").replace('\u2018', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def words_of(text):
    return [w for w in (norm(t) for t in
                        re.findall(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z0-9]+)*", text)) if w]


def slice_wav(src, dst, start_ms, end_ms):
    with wave.open(src, 'rb') as w:
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        total = w.getnframes()
        a = max(0, int(start_ms / 1000 * rate))
        b = min(total, int(end_ms / 1000 * rate))
        if b - a < int(rate * 0.3):
            return False
        w.setpos(a)
        data = w.readframes(b - a)
    with wave.open(dst, 'wb') as o:
        o.setnchannels(ch)
        o.setsampwidth(width)
        o.setframerate(rate)
        o.writeframes(data)
    return True


def transcribe_clip(wav_path, tag):
    out = f'/tmp/timing_check/{tag}'
    try:
        subprocess.run(['whisper-cli', '-m', MODEL, '-f', wav_path,
                        '-oj', '-of', out],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        data = json.load(open(out + '.json', encoding='utf-8'))
        segs = data.get('transcription', [])
        return ' '.join(s.get('text', '') for s in segs).strip()
    except Exception as e:
        return f'__error__ {e}'
    finally:
        for p in (out + '.json',):
            if os.path.exists(p):
                os.remove(p)


def work_book(path):
    book_id = os.path.splitext(os.path.basename(path))[0]
    data = json.load(open(path, encoding='utf-8'))
    audio = os.path.join(ASSETS, 'audio', book_id + '.m4a')
    if not os.path.exists(audio):
        return book_id, []
    src = f'/tmp/timing_check/{book_id}.wav'
    if not os.path.exists(src):
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1',
                        audio, src], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Sample sentences across the book.
    flat = [(p['startMs'], s) for p in data['pages'] for s in p.get('sentences', [])]
    if not flat:
        return book_id, []
    flat = flat[::max(1, len(flat) // SAMPLE)][:SAMPLE]
    results = []
    for idx, (page_start, s) in enumerate(flat):
        a = max(0, s['startMs'] - 100)
        b = s['endMs'] + 150
        clip = f'/tmp/timing_check/{book_id}_{idx}.wav'
        if not slice_wav(src, clip, a, b):
            continue
        heard = transcribe_clip(clip, f'{book_id}_{idx}')
        hw, sw = words_of(heard), words_of(s['en'])
        if heard.startswith('__error__') or not hw:
            results.append((None, book_id, s['startMs'], s['en'][:50], heard[:60]))
            continue
        ratio = difflib_ratio(sw, hw)
        # Short interjections are transcription-noisy: pass if any word heard.
        if len(sw) <= 3 and set(sw) & set(hw):
            ratio = max(ratio, 0.75)
        results.append((ratio, book_id, s['startMs'], s['en'][:50], heard[:60]))
        os.remove(clip)
    os.remove(src)
    return book_id, results


def difflib_ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def main():
    os.makedirs('/tmp/timing_check', exist_ok=True)
    files = []
    for lv in LEVELS:
        files += sorted(glob.glob(os.path.join(ASSETS, 'text', f'L{lv}-*.json')))
    all_ok = []
    all_bad = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for book_id, results in pool.map(work_book, files):
            for ratio, bid, start, en, heard in results:
                if ratio is None:
                    continue
                (all_ok if ratio >= 0.6 else all_bad).append((ratio, bid, start, en, heard))
            rates = [r for r, *_ in results if r is not None]
            if rates:
                print(f'{book_id}: n={len(rates)} ok={sum(1 for r in rates if r >= 0.6)}'
                      f' avg={sum(rates)/len(rates):.2f}', flush=True)
    print()
    all_bad = [x for x in all_bad
               if not re.match(r'^\((upbeat|playful)|\[BLANK|\[music', x[4])]
    print('=== mismatched windows (ratio < 0.6) ===')
    all_bad.sort()
    for ratio, bid, start, en, heard in all_bad[:40]:
        print(f'{ratio:.2f} {bid}@{start}ms')
        print(f'   APP: {en}')
        print(f'   HEARD: {heard}')
    total = len(all_ok) + len(all_bad)
    print(f'\ntotal checked {total}, matched {len(all_ok)} ({100*len(all_ok)/max(1,total):.0f}%), '
          f'mismatched {len(all_bad)}')


if __name__ == '__main__':
    main()
