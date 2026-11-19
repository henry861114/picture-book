#!/usr/bin/env python3
"""Re-encode the Oxford MP3s to compact mono AAC (.m4a).

The originals are 64 kbps stereo speech. 32 kbps mono AAC keeps speech clear
and cuts the audio payload roughly in half. The original MP3s are moved to
``audio_mp3_original/`` outside the assets tree as a backup.
"""
import glob
import json
import os
import shutil
import subprocess

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(PROJECT, 'app/src/main/assets/oxford')
AUDIO = os.path.join(ASSETS, 'audio')
BACKUP = os.path.join(PROJECT, 'audio_mp3_original')
LIBRARY = os.path.join(ASSETS, 'library.json')

os.makedirs(BACKUP, exist_ok=True)
mp3s = sorted(glob.glob(os.path.join(AUDIO, '*.mp3')) + glob.glob(os.path.join(AUDIO, '*.MP3')))
print('MP3 files:', len(mp3s))
converted = 0
for mp3 in mp3s:
    base = os.path.splitext(os.path.basename(mp3))[0]
    out = os.path.join(AUDIO, base + '.m4a')
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        subprocess.run([
            'afconvert', '-f', 'm4af', '-d', 'aac', '-b', '32000', '-c', '1',
            mp3, out
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.getsize(out) > os.path.getsize(mp3):
        print('warning: output larger than input for', base)
    converted += 1
    if converted % 20 == 0:
        print('converted', converted, '/', len(mp3s))

# Update the library index before moving the originals.
with open(LIBRARY, encoding='utf-8') as f:
    library = json.load(f)
for level in library.get('levels', []):
    for book in level.get('books', []):
        audio = book.get('audio')
        if audio and audio.lower().endswith('.mp3'):
            book['audio'] = audio[:-4] + '.m4a'
with open(LIBRARY, 'w', encoding='utf-8') as f:
    json.dump(library, f, ensure_ascii=False, indent=2, sort_keys=True)

# Move originals out of the assets tree.
for mp3 in mp3s:
    target = os.path.join(BACKUP, os.path.basename(mp3))
    if os.path.exists(target):
        os.remove(mp3)
    else:
        shutil.move(mp3, target)

print('done; originals moved to', BACKUP)
