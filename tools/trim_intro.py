#!/usr/bin/env python3
"""Remove the narrated title/instructions at the start of every audiobook.

The first real sentence time comes from the word-level alignment. We trim the
M4A from that point, then subtract the intro duration from every page and
sentence timestamp so playback and highlighting still match.
"""
import glob
import json
import os
import re
import shutil
import subprocess

ASSETS = 'app/src/main/assets/oxford'
TEXT_ROOT = os.path.join(ASSETS, 'text')
AUDIO_ROOT = os.path.join(ASSETS, 'audio')
BACKUP = 'audio_m4a_untrimmed'
TMP = '/tmp/oxford_trim'


def afinfo(path):
    out = subprocess.check_output(['afinfo', path], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore')
    duration = 0.0
    rate = 44100
    m = re.search(r'estimated duration:\s*([\d.]+)\s*sec', out)
    if m:
        duration = float(m.group(1))
    m = re.search(r'(\d+)\s*Hz', out)
    if m:
        rate = int(m.group(1))
    return duration, rate


def main():
    os.makedirs(BACKUP, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    report = {}
    for path in sorted(glob.glob(os.path.join(TEXT_ROOT, '*.json'))):
        book_id = os.path.splitext(os.path.basename(path))[0]
        data = json.load(open(path, encoding='utf-8'))
        pages = data['pages']
        starts = [s.get('startMs', -1) for p in pages for s in p.get('sentences', [])
                  if s.get('startMs', -1) >= 0]
        if not starts:
            continue
        story_start = min(starts)
        if story_start <= 3000:
            report[book_id] = {'start': 0}
            continue
        audio = os.path.join(AUDIO_ROOT, book_id + '.m4a')
        if not os.path.exists(audio):
            continue
        duration, rate = afinfo(audio)
        if duration <= 0 or story_start / 1000.0 >= duration - 5:
            continue
        offset_frames = int(round(story_start / 1000.0 * rate))
        tmp_out = os.path.join(TMP, book_id + '.m4a')
        try:
            subprocess.run([
                'afconvert', '-f', 'm4af', '-d', 'aac', '-b', '32000', '-c', '1',
                '--offset', str(offset_frames), audio, tmp_out
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print('trim failed', book_id, e)
            continue
        if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) == 0:
            print('empty trim', book_id)
            continue
        backup = os.path.join(BACKUP, book_id + '.m4a')
        if not os.path.exists(backup):
            shutil.copyfile(audio, backup)
        shutil.move(tmp_out, audio)
        new_duration, _ = afinfo(audio)

        # Shift page/sentence times.
        first_story_page = None
        for pi, page in enumerate(pages):
            if page.get('sentences'):
                first_story_page = pi
                break
        for pi, page in enumerate(pages):
            if page.get('sentences'):
                ps = max(0, int(page.get('startMs', 0)) - story_start)
                pe = max(ps + 1, int(page.get('endMs', 0)) - story_start)
                page['startMs'] = ps
                page['endMs'] = min(pe, int(new_duration * 1000))
            else:
                if first_story_page is not None and pi < first_story_page:
                    page['startMs'] = 0
                    page['endMs'] = 100
                else:
                    page['startMs'] = max(0, int(page.get('startMs', 0)) - story_start)
                    page['endMs'] = max(page['startMs'] + 1,
                                        int(page.get('endMs', 0)) - story_start)
            for s in page.get('sentences', []):
                if s.get('startMs', -1) >= 0:
                    s['startMs'] = max(0, s['startMs'] - story_start)
                    s['endMs'] = max(s['startMs'] + 1, s['endMs'] - story_start)
                    if s['endMs'] > int(new_duration * 1000):
                        s['endMs'] = int(new_duration * 1000)
        json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        report[book_id] = {'start': story_start, 'duration': new_duration}
        print('trimmed', book_id, 'intro', round(story_start / 1000, 1), 's', flush=True)

    json.dump(report, open('/tmp/intro_trim.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('done; trimmed books:', sum(1 for v in report.values() if v.get('start', 0) > 0))


if __name__ == '__main__':
    main()
