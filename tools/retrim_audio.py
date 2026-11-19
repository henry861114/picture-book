#!/usr/bin/env python3
"""Re-trim the audiobooks for the given levels to the true story start."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

ASSETS = 'app/src/main/assets/oxford'
TEXT_ROOT = os.path.join(ASSETS, 'text')
AUDIO_ROOT = os.path.join(ASSETS, 'audio')
BACKUP = 'audio_m4a_untrimmed'
TMP = '/tmp/oxford_retrim'


def afinfo(path):
    out = subprocess.check_output(['afinfo', path], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore')
    m = re.search(r'estimated duration:\s*([\d.]+)\s*sec', out)
    duration = float(m.group(1)) if m else 0.0
    m = re.search(r'(\d+)\s*Hz', out)
    rate = int(m.group(1)) if m else 44100
    return duration, rate


def main():
    levels = sys.argv[1:] or ['5', '6']
    os.makedirs(BACKUP, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    old_trim = {}
    tp = '/tmp/intro_trim.json'
    if os.path.exists(tp):
        old_trim = json.load(open(tp, encoding='utf-8'))
    for level in levels:
        for path in sorted(glob.glob(os.path.join(TEXT_ROOT, f'L{level}-*.json'))):
            book_id = os.path.splitext(os.path.basename(path))[0]
            data = json.load(open(path, encoding='utf-8'))
            starts = [s.get('startMs', -1) for p in data['pages'] for s in p.get('sentences', [])
                      if s.get('startMs', -1) >= 0]
            new_start = min(starts) if starts else 0
            old_start = int(old_trim.get(book_id, {}).get('start', 0))
            audio = os.path.join(AUDIO_ROOT, book_id + '.m4a')
            if not os.path.exists(audio):
                continue
            backup = os.path.join(BACKUP, book_id + '.m4a')
            if os.path.exists(backup):
                source = backup
            elif int(old_trim.get(book_id, {}).get('start', 0)) <= 3000:
                # First trim for this book (asset is still untrimmed): keep a
                # copy first so repeated runs always re-cut from the original.
                shutil.copyfile(audio, backup)
                source = audio
            else:
                # The asset was trimmed in an earlier pass and no untrimmed
                # copy exists. Cutting again would corrupt it; the transcript
                # for this book must already match the trimmed audio.
                print('skip (no untrimmed backup):', book_id, flush=True)
                continue
            if new_start <= 3000:
                # No intro to remove. Only restore the untrimmed backup when
                # the asset is actually shorter than it (i.e. it was
                # previously over-cut); never touch a correct asset.
                if os.path.exists(backup) and os.path.exists(audio):
                    dur_audio, _ = afinfo(audio)
                    dur_backup, _ = afinfo(backup)
                    if 0 < dur_audio < dur_backup - 5:
                        shutil.copyfile(backup, audio)
                # Times stay as they are (already near zero).
                continue
            duration, rate = afinfo(source)
            if duration <= 0 or new_start / 1000.0 >= duration - 5:
                continue
            offset_frames = int(round(new_start / 1000.0 * rate))
            tmp_out = os.path.join(TMP, book_id + '.m4a')
            try:
                subprocess.run([
                    'afconvert', '-f', 'm4af', '-d', 'aac', '-b', '32000', '-c', '1',
                    '--offset', str(offset_frames), source, tmp_out
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print('retrim failed', book_id, e)
                continue
            if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) == 0:
                continue
            shutil.move(tmp_out, audio)
            new_duration, _ = afinfo(audio)
            old_trim[book_id] = {'start': new_start, 'duration': new_duration}
            json.dump(old_trim, open(tp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            for page in data['pages']:
                ps = max(0, int(page.get('startMs', 0)) - new_start)
                pe = max(ps + 1, int(page.get('endMs', 0)) - new_start)
                page['startMs'] = ps
                page['endMs'] = min(pe, int(new_duration * 1000))
                for s in page.get('sentences', []):
                    if s.get('startMs', -1) >= 0:
                        s['startMs'] = max(0, s['startMs'] - new_start)
                        s['endMs'] = max(s['startMs'] + 1, s['endMs'] - new_start)
                        if s['endMs'] > int(new_duration * 1000):
                            s['endMs'] = int(new_duration * 1000)
            json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
            print('retrimmed', book_id, 'start', round(new_start / 1000, 1), 's',
                  'duration', round(new_duration, 1), 's', flush=True)


if __name__ == '__main__':
    main()
