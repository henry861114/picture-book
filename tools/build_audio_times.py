#!/usr/bin/env python3
"""Estimate page start/end times inside each whole-book MP3.

The Oxford MP3s are one file per book, not one file per page. We estimate the
page boundaries from the amount of text on each page, then snap the estimate to
nearby long pauses in the audio. The result is stored in each text JSON page as
startMs/endMs and is used for auto page-turning.
"""
import glob
import json
import math
import os
import re
import struct
import subprocess
import sys
import wave

AUDIO_ROOT = 'app/src/main/assets/oxford/audio'
TEXT_ROOT = 'app/src/main/assets/oxford/text'
WHISPER_ROOT = '/tmp/oxford_whisper'
TMP_WAV = '/tmp/oxford_times.wav'

META = [
    'stage ', 'kipper stories', 'more stories', 'first sentences', 'first words',
    'this story is called', 'written by', 'illustrated by',
    'when you hear this sound', 'turn the page', 'now open the book',
    "let's look at the pictures", 'lets look at the pictures',
    "let's read the story", 'lets read the story', 'let us read the story',
    'what do you think', 'can you find', 'look at the pictures',
    'oxford reading tree', 'biff, chip and kipper', 'read the story together',
]


def story_start_seconds(book_id):
    """Start of the first real story line in the audiobook, in seconds."""
    path = os.path.join(WHISPER_ROOT, book_id + '.json')
    if not os.path.exists(path):
        return 0.0
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        return 0.0
    for seg in data.get('transcription', []):
        text = (seg.get('text') or '').strip().lower()
        if not text or any(m in text for m in META):
            continue
        return seg.get('offsets', {}).get('from', 0) / 1000.0
    return 0.0


def audio_duration(path):
    out = subprocess.check_output(['afinfo', path], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore')
    m = re.search(r'estimated duration:\s*([\d.]+)\s*sec', out)
    return float(m.group(1)) if m else 0.0


def decode(path):
    if os.path.exists(TMP_WAV):
        os.remove(TMP_WAV)
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', path, TMP_WAV],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def silence_runs(wav_path):
    with wave.open(wav_path, 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
        data = w.readframes(n)
    win = max(1, int(sr * 0.05))
    runs = []
    start = None
    # 16-bit mono little endian
    for i in range(0, len(data) - win * 2 + 1, win * 2):
        chunk = data[i:i + win * 2]
        s = 0
        for j in range(0, len(chunk), 2):
            v = struct.unpack_from('<h', chunk, j)[0]
            s += v * v
        rms = math.sqrt(s / max(1, len(chunk) // 2)) / 32768.0
        t = i / 2 / sr
        if rms < 0.008:
            if start is None:
                start = t
        else:
            if start is not None:
                length = t - start
                if length >= 0.25:
                    runs.append((start, t, length))
                start = None
    if start is not None:
        t = len(data) / 2 / sr
        if t - start >= 0.25:
            runs.append((start, t, t - start))
    return runs


BACK_MATTER = [
    'play a game', 'find the word', 'talk together', 'this story practises',
    'book band', 'isbn', 'available in packs', 'teaching notes',
    'word recognition', 'language comprehension', 'read the story',
]


def page_weights(pages):
    weights = []
    for i, page in enumerate(pages):
        text = ' '.join(s.get('en', '') for s in page.get('sentences', []))
        if any(k in text.lower() for k in BACK_MATTER):
            weights.append(1)
            continue
        w = len(text)
        if w == 0:
            w = 2 if i == 0 else 1
        elif w < 5:
            w = 5
        weights.append(w)
    return weights


def process(book_id, pages, audio_path):
    duration = audio_duration(audio_path)
    if duration <= 0:
        return None
    try:
        decode(audio_path)
        silences = silence_runs(TMP_WAV)
    except Exception as e:
        print('audio decode failed', book_id, e)
        silences = []

    total_text = sum(
        len(' '.join(s.get('en', '') for s in page.get('sentences', [])))
        for page in pages
    )
    first_text_page = next(
        (i for i, page in enumerate(pages) if page.get('sentences')), 0)
    hint_start = story_start_seconds(book_id)
    if 3.0 < hint_start < duration - 5.0 and first_text_page > 0:
        # The audiobook has an intro (title, instructions, page-turn prompts).
        # Keep the intro on the first pages, then distribute the remaining
        # audio over the story pages.
        intro_pages = first_text_page
        story_pages = pages[intro_pages:]
        story_weights = page_weights(story_pages)
        total_story = sum(story_weights) or 1
        weights = [1] * intro_pages + story_weights
        targets = []
        for i in range(intro_pages):
            targets.append(hint_start * (i + 1) / max(1, intro_pages))
        acc = 0
        for w in story_weights:
            acc += w
            targets.append(hint_start + (duration - hint_start) * acc / total_story)
    else:
        weights = [1] * len(pages) if total_text < 40 else page_weights(pages)
        total_w = sum(weights) or 1
        # Cumulative target times for the end of every page.
        targets = []
        acc = 0
        for w in weights:
            acc += w
            targets.append(duration * acc / total_w)

    total_w = sum(weights) or 1

    # Candidate silence centers, excluding the first/last second.
    candidates = []
    for start, end, length in silences:
        center = (start + end) / 2.0
        if 0.5 < center < duration - 0.3:
            candidates.append(center)
    candidates = sorted(set(round(c, 2) for c in candidates))

    # Snap each target to the nearest unused pause, within a generous window.
    boundaries = []
    used = set()
    prev = 0.0
    for idx, target in enumerate(targets):
        if idx == len(targets) - 1:
            boundaries.append(duration)
            continue
        prev_weight = weights[idx]
        page_guess = duration * prev_weight / total_w
        window = max(2.0, min(8.0, page_guess * 0.55))
        best = None
        best_dist = 1e9
        for c in candidates:
            if c in used:
                continue
            if c <= prev + 0.8 or c >= duration - 0.3:
                continue
            dist = abs(c - target)
            if dist < best_dist and dist <= window:
                best = c
                best_dist = dist
        if best is None:
            best = max(prev + 0.8, target)
        best = min(best, duration - 0.3)
        if best <= prev + 0.5:
            best = prev + 0.5
        boundaries.append(best)
        used.add(best)
        prev = best

    times = []
    start_t = 0.0
    for end_t in boundaries:
        times.append((int(round(start_t * 1000)), int(round(end_t * 1000))))
        start_t = end_t
    return times


def main():
    files = sorted(glob.glob(os.path.join(TEXT_ROOT, '*.json')))
    for n, path in enumerate(files, 1):
        book_id = os.path.splitext(os.path.basename(path))[0]
        data = json.load(open(path))
        pages = data['pages']
        audio_path = os.path.join(AUDIO_ROOT, book_id + '.m4a')
        if not os.path.exists(audio_path):
            audio_path = os.path.join(AUDIO_ROOT, book_id + '.mp3')
        if not os.path.exists(audio_path):
            audio_path = os.path.join(AUDIO_ROOT, book_id + '.MP3')
        if not os.path.exists(audio_path):
            print('missing audio', book_id)
            continue
        times = process(book_id, pages, audio_path)
        if times is None:
            print('no duration', book_id)
            continue
        for page, (start, end) in zip(pages, times):
            page['startMs'] = start
            page['endMs'] = end
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if n % 10 == 0:
            print(f'times progress: {n}/{len(files)}')
            sys.stdout.flush()
    print('audio times complete')


if __name__ == '__main__':
    main()
