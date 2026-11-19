#!/usr/bin/env python3
"""Refine sentence times against the real audio with clip matching.

Whisper word timestamps drift by seconds in music-heavy books. Short clips,
however, transcribe with reliable local timing. For every sentence we:

1. cut [start-100, end+150] from the (trimmed) audio and transcribe it;
2. if the clip text matches the sentence, keep the window (optionally
   tightened to the matched words inside the clip);
3. otherwise search +-4/8/12/16/20 s shifts for the first matching window;
4. write the refined startMs/endMs and rebuild the page windows.

Only times change; the sentence text and translations are untouched.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

ASSETS = 'app/src/main/assets/oxford'
MODEL = os.environ.get('WHISPER_MODEL', '/tmp/ggml-base.en.bin')
LEVELS = sys.argv[1:] or ['5', '6']
TMP = '/tmp/refine_clip'
os.makedirs(TMP, exist_ok=True)


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
        if b - a < int(rate * 0.4):
            return False
        w.setpos(a)
        data = w.readframes(b - a)
    with wave.open(dst, 'wb') as o:
        o.setnchannels(ch)
        o.setsampwidth(width)
        o.setframerate(rate)
        o.writeframes(data)
    return True


def transcribe(wav_path, tag, word_level=False):
    """Return (text, words-with-local-times)."""
    out = os.path.join(TMP, tag)
    cmd = ['whisper-cli', '-m', MODEL, '-f', wav_path, '-oj', '-of', out]
    if word_level:
        cmd += ['-ml', '1', '-sow']
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        data = json.load(open(out + '.json', encoding='utf-8'))
        segs = data.get('transcription', [])
        text = ' '.join(s.get('text', '') for s in segs).strip()
        words = []
        for s in segs:
            w = norm(s.get('text', ''))
            if w:
                words.append((w, int(s['offsets']['from']), int(s['offsets']['to'])))
        return text, words
    except Exception:
        return '', []
    finally:
        if os.path.exists(out + '.json'):
            os.remove(out + '.json')


NOISE = re.compile(r'^\((upbeat|playful|gentle|soft)|\[BLANK|\[music|♪', re.I)


def match_quality(sentence_words, heard_words):
    """0..1 similarity that tolerates extra heard words and noise."""
    if not sentence_words or not heard_words:
        return 0.0
    import difflib
    ratio = difflib.SequenceMatcher(None, sentence_words, heard_words).ratio()
    # Tolerate surrounding narration in the clip: best sliding containment.
    n, m = len(sentence_words), len(heard_words)
    best = ratio
    for i in range(max(1, m - n + 1)):
        seg = heard_words[i:i + n]
        r = difflib.SequenceMatcher(None, sentence_words, seg).ratio()
        best = max(best, r)
    if len(sentence_words) <= 3 and set(sentence_words) & set(heard_words):
        best = max(best, 0.8)
    return best


def locate_in_clip(sentence_words, clip_words):
    """Find the sentence inside clip words; return (start, end) local ms."""
    import difflib
    n = len(sentence_words)
    best = (None, -1, None, None)
    for i in range(len(clip_words) - n + 1):
        seg = [w for w, _, _ in clip_words[i:i + n]]
        r = difflib.SequenceMatcher(None, sentence_words, seg).ratio()
        if r > best[1]:
            best = (i, r, clip_words[i][1], clip_words[i + n - 1][2])
    if best[1] >= 0.7:
        return best[2], best[3]
    return None


ATTRIB = re.compile(r'^(Said|Asked|Called|Shouted|Cried|Laughed|Whispered|Screamed|'
                    r'Groaned|Moaned|Yelled|Replied|Answered|Wailed|Sniffed)\b')
TERM = ('.', '!', '?')


def merge_fragments(data):
    """Merge ASR-split fragments: "Off you go," + "Called Mrs." + "May."

    Dialogue and its attribution are one spoken utterance; keeping them
    apart leaves windows too short to align and awkward display lines.
    """
    merged = 0
    for page in data['pages']:
        sents = page.get('sentences', [])
        out = []
        i = 0
        while i < len(sents):
            cur = sents[i]
            j = i
            while j + 1 < len(sents):
                nxt = sents[j + 1]
                en_c = cur.get('en', '').strip()
                en_n = nxt.get('en', '').strip()
                if not en_c or not en_n:
                    break
                wc, wn = len(words_of(en_c)), len(words_of(en_n))
                if wc + wn > 40:
                    break
                if re.search(r'\b(Said|Asked|Called|Shouted|Cried|Laughed|Whispered|'
                             r'Replied|Answered)\w*\.?$', en_c, re.I):
                    break  # already ends with its attribution
                cond = False
                if not en_c.endswith(TERM) and (wn <= 3 or en_n[:1].islower()):
                    cond = True
                elif wn <= 3 and (ATTRIB.match(en_n) or en_n[:1].islower()):
                    cond = True
                elif wc <= 3 and ATTRIB.match(en_c) and wn <= 3:
                    cond = True
                if not cond:
                    break
                if en_c.endswith(',') and ATTRIB.match(en_n):
                    en_n = en_n[0].lower() + en_n[1:]
                zh_c = (cur.get('zh') or '').strip()
                zh_n = (nxt.get('zh') or '').strip()
                cur = {'en': (en_c + ' ' + en_n).strip(),
                       'zh': (zh_c + ' ' + zh_n).strip(),
                       'startMs': min(cur['startMs'], nxt['startMs']),
                       'endMs': max(cur['endMs'], nxt['endMs'])}
                j += 1
                merged += 1
            out.append(cur)
            i = j + 1
        page['sentences'] = out
    return merged


def work_book(path):
    book_id = os.path.splitext(os.path.basename(path))[0]
    data = json.load(open(path, encoding='utf-8'))
    merged = merge_fragments(data)
    audio = os.path.join(ASSETS, 'audio', book_id + '.m4a')
    src = os.path.join(TMP, book_id + '.wav')
    if not os.path.exists(src):
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1',
                        audio, src], check=True, capture_output=True)
    with wave.open(src, 'rb') as w:
        duration_ms = int(w.getnframes() / w.getframerate() * 1000)

    flat = [(s, pi) for pi, p in enumerate(data['pages'])
            for s in p.get('sentences', [])]
    changed = 0
    shifts_used = {}
    prev_end = -1
    for s, pi in flat:
        en = s.get('en', '')
        sw = words_of(en)
        if not sw or s.get('startMs', -1) < 0:
            prev_end = max(prev_end, s.get('endMs', 0))
            continue
        a, b = s['startMs'], s['endMs']
        final = None
        for delta in (0, -4, 4, -8, 8, -12, 12, -16, 16, -20, 20):
            ca = max(0, a + delta * 1000 - 100)
            cb = min(duration_ms, b + delta * 1000 + 150)
            if cb - ca < 500:
                continue
            tag = f'{book_id}_{id(s)&0xffff}_{delta}'
            clip_path = os.path.join(TMP, tag + '.wav')
            if not slice_wav(src, clip_path, ca, cb):
                continue
            text, cwords = transcribe(clip_path, tag, word_level=True)
            if os.path.exists(clip_path):
                os.remove(clip_path)
            if not cwords:
                continue
            if NOISE.match(text.strip()):
                continue
            hw = [w for w, _, _ in cwords]
            q = match_quality(sw, hw)
            if q < 0.55:
                continue
            span = locate_in_clip(sw, cwords)
            if span:
                ns = max(0, ca + span[0] - 40)
                ne = min(duration_ms, ca + span[1] + 60)
            else:
                ns, ne = max(0, a + delta * 1000), b + delta * 1000
            if ne - ns < 200:
                ne = ns + 200
            final = (ns, ne)
            if delta:
                shifts_used[delta] = shifts_used.get(delta, 0) + 1
            break
        if final:
            ns, ne = final
            ns = max(ns, prev_end + 30)
            if abs(ns - a) > 80 or abs(ne - b) > 80:
                changed += 1
            s['startMs'], s['endMs'] = ns, ne
            prev_end = ne
        else:
            s['startMs'], s['endMs'] = a, b
            prev_end = max(prev_end, b)

    # Rebuild page windows from refined sentence times.
    for p in data['pages']:
        if p.get('sentences'):
            p['startMs'] = max(0, min(s['startMs'] for s in p['sentences']) - 150)
            p['endMs'] = max(s['endMs'] for s in p['sentences']) + 350
    os.remove(src)
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return book_id, changed, len(flat), shifts_used, merged


def main():
    files = []
    for lv in LEVELS:
        files += sorted(glob.glob(os.path.join(ASSETS, 'text', f'L{lv}-*.json')))
    print('books:', len(files), flush=True)
    total_changed = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(work_book, p): p for p in files}
        for fut in as_completed(futures):
            try:
                book_id, changed, total, shifts, merged = fut.result()
            except Exception as e:
                print('FAILED', futures[fut], e, flush=True)
                continue
            total_changed += changed
            print(f'{book_id}: refined {changed}/{total} merged={merged} shifts={shifts}', flush=True)
    print('total refined:', total_changed)


if __name__ == '__main__':
    main()
