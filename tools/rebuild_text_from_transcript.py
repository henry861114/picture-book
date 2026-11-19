#!/usr/bin/env python3
"""Rebuild page text for the given levels from the word-level transcript.

The printed OCR text is kept when it matches the narration; pages whose OCR
text is missing or clearly different use the transcript text instead. Every
sentence gets its exact word-level start/end time, so text and audio match.
Times are still in the original (untrimmed) audio timeline.
"""
import difflib
import glob
import json
import os
import re
import sys

ASSETS = 'app/src/main/assets/oxford'
TEXT_ROOT = os.path.join(ASSETS, 'text')
WORD_ROOT = os.environ.get('WORD_ROOT', '/tmp/oxford_words_all')
SEG_ROOT = os.environ.get('SEG_ROOT', '/tmp/oxford_whisper')

META = [
    'stage', 'stories', 'this story is called', 'written by', 'illustrated by',
    'when you hear', 'turn the page', 'now open the book',
    "let's read the story", "let's look at the pictures",
    'what will happen in this story', 'read the story together',
    'oxford reading tree', 'biff, chip and kipper',
]

TAIL_META = [
    'play a game', 'find the word', 'talk together', 'this story practises',
    'book band', 'isbn', 'available in packs', 'teaching notes',
    'word recognition', 'language comprehension', 'read the story',
]

INTRO_TAIL = [
    r'story together', r'read the story', r'turn the page', r'open the book',
    r'this sound', r'pictures together', r'written by', r'illustrated by',
    r'story is called', r'see what will happen',
]

ASR_FIX = [
    (r'\bget beef\b', 'get Biff'),
    (r'\bShe liked the program\b\.?', 'He liked the programme.'),
    (r'\bBif\b', 'Biff'),
    (r'\bGip\b', 'Chip'),
    (r'\bNadine\b', 'Nadim'),
    (r'\bAnina\b', 'Anneena'),
    (r'\bRodra Kant\b', 'Roderick Hunt'),
    (r'\bRoger Hunt\b', 'Roderick Hunt'),
    (r'\bRodrik Hunt\b', 'Roderick Hunt'),
    (r'\bBrickta\b', 'Brychta'),
    (r'\bFricta\b', 'Brychta'),
    (r'\bBricda\b', 'Brychta'),
    (r'\bBrikta\b', 'Brychta'),
    (r'\bPricta\b', 'Brychta'),
    (r'\bKeeper\b', 'Kipper'),
    (r'\bMom\b', 'Mum'),
]

NAME_CAPS = {
    'biff': 'Biff', 'chip': 'Chip', 'kipper': 'Kipper', 'wilf': 'Wilf',
    'wilma': 'Wilma', 'floppy': 'Floppy', 'nadim': 'Nadim',
    'anneena': 'Anneena', 'gran': 'Gran', 'mum': 'Mum', 'dad': 'Dad',
    'jo': 'Jo', 'jones': 'Jones', 'arthur': 'Arthur', 'noah': 'Noah',
    'fred': 'Fred', 'blot': 'Blot', 'vicky': 'Vicky', 'oprah': 'Oprah',
}


def norm(text):
    text = (text or '').lower().replace('’', "'").replace('‘', "'")
    return re.sub(r"[^a-z0-9']", '', text)


def is_meta(text):
    low = text.lower()
    return any(m in low for m in META) or not re.search(r'[a-z]', low)


def is_tail_meta(text):
    low = text.lower()
    return any(m in low for m in TAIL_META)


def fix_asr(text):
    for pattern, replacement in ASR_FIX:
        text = re.sub(pattern, replacement, text, flags=re.I)
    tokens = text.split(' ')
    fixed = []
    for t in tokens:
        low = t.lower()
        if low in NAME_CAPS:
            fixed.append(NAME_CAPS[low])
        elif low == 'i':
            fixed.append('I')
        else:
            fixed.append(t)
    text = ' '.join(fixed)
    text = re.sub(r'(^|[.!?]"?\s+)([a-z])',
                  lambda m: m.group(1) + m.group(2).upper(), text)
    if text and text[-1] not in '.!?"”’':
        text += '.'
    return text


def strip_intro_tail(text):
    """Remove leftover narration instructions at the start of a sentence."""
    for _ in range(6):
        hit = None
        low = text.lower()
        for pattern in INTRO_TAIL:
            m = re.search(pattern, low)
            if m and (hit is None or m.start() < hit.start()):
                hit = m
        if not hit or hit.start() > 200:
            break
        tail = text[hit.end():]
        pm = re.search(r'[.!?]', tail)
        if pm:
            text = tail[pm.end():].strip()
        else:
            text = tail.strip()
    return text


def load_raw_tokens(book_id):
    data = json.load(open(os.path.join(WORD_ROOT, book_id + '.json'), encoding='utf-8'))
    out = []
    for seg in data.get('transcription', []):
        raw = seg.get('text', '').strip()
        if not raw:
            continue
        out.append((norm(raw), int(seg['offsets']['from']), int(seg['offsets']['to']), raw))
    return out


STRONG_INTRO = [
    'open the book', 'turn the page', 'read the story together',
    'read the story alone', 'what will happen', 'hear this sound',
    'hear the chime', 'follow the pictures',
]


def story_min_time(book_id, raw_tokens):
    """Where the story narration starts (intro announcements excluded).

    Primary method: scan the word stream itself for the read-aloud
    instructions that end every intro ("Now open the book", "turn the
    page", ...) — works with any transcript source. Falls back to the
    paragraph-level transcript when the word stream has no markers.
    """
    head = [raw for _, _, _, raw in raw_tokens[:90]]
    joined = ' '.join(head)

    def phrase_end(pattern):
        matches = list(re.finditer(pattern, joined, flags=re.I))
        if not matches:
            return 0
        m = matches[-1]
        consumed = 0
        for i, raw in enumerate(head):
            consumed += len(raw) + 1
            if consumed >= m.end():
                return int(raw_tokens[i][2])
        return 0

    strong_end = max(phrase_end(p) for p in STRONG_INTRO)
    if strong_end:
        return strong_end
    # Fallback: paragraph transcript meta detection (old behaviour).
    path = os.path.join(SEG_ROOT, book_id + '.json')
    if not os.path.exists(path):
        return 0
    data = json.load(open(path, encoding='utf-8'))
    segments = [seg for seg in data.get('transcription', [])
                if seg.get('text', '').strip()]
    strong_end = 0
    for seg in segments[:20]:
        low = seg['text'].lower()
        if any(m in low for m in STRONG_INTRO):
            strong_end = max(strong_end, int(seg['offsets']['to']))
    if strong_end:
        return strong_end
    # Last resort: end of the last meta announcement before the story.
    last_meta_end = 0
    checked = 0
    for seg in segments:
        text = seg.get('text', '').strip()
        checked += 1
        if checked > 14:
            break
        if is_meta(text):
            last_meta_end = max(last_meta_end, int(seg['offsets']['to']))
        elif not is_tail_meta(text) and len(text) > 12:
            break
    return last_meta_end


def build_sentences(raw_tokens, min_time):
    groups = []
    current = []
    prev_end = None
    for w, start, end, raw in raw_tokens:
        if start < min_time:
            if current:
                groups.append(current)
                current = []
                prev_end = None
            continue
        if prev_end is not None and start - prev_end > 800 and current:
            groups.append(current)
            current = []
        current.append((w, start, end, raw))
        last_char = raw.strip()[-1] if raw.strip() else ''
        if last_char in '.!?"”’':
            groups.append(current)
            current = []
            prev_end = None
        else:
            prev_end = end
    if current:
        groups.append(current)

    result = []
    for group in groups:
        if not group:
            continue
        text = fix_asr(' '.join(g[3].strip() for g in group))
        text = strip_intro_tail(text)
        words = [norm(t) for t in re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*", text)]
        words = [w for w in words if w]
        if not words:
            continue
        start = max(0, group[0][1] - 40)
        end = group[-1][2] + 60
        if end <= start:
            end = start + 200
        result.append({'text': text, 'norm': words,
                       'start': start, 'end': end})
    return result


def load_ocr_pages(book_id):
    """Original OCR page mapping (before any cleanup), used for page anchors."""
    raw_path = f'/tmp/oxford_text_raw/{book_id}.json'
    if os.path.exists(raw_path):
        source = raw_path
    else:
        source = os.path.join(TEXT_ROOT, book_id + '.json')
    data = json.load(open(source, encoding='utf-8'))
    pages = []
    for page in data['pages']:
        ocrs = []
        for s in page.get('sentences', []):
            words = [norm(t) for t in re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*", s.get('en', ''))]
            words = [w for w in words if w]
            if words:
                ocrs.append({'words': words, 'en': s.get('en', ''), 'zh': s.get('zh', '')})
        pages.append(ocrs)
    return pages


def best_zh(words, zh_source):
    if not zh_source:
        return ''
    best = None
    for norm_en, zh in zh_source:
        if not zh:
            continue
        sim = difflib.SequenceMatcher(None, words, norm_en).ratio()
        if best is None or sim > best[0]:
            best = (sim, zh)
    if best and best[0] >= 0.6:
        return best[1]
    return ''


def clean_display_en(text):
    tokens = text.split(' ')
    out = []
    started = False
    for t in tokens:
        stripped = t.strip()
        core = re.sub(r"[^A-Za-z0-9']", '', stripped)
        if not started:
            if not core:
                continue
            if re.match(r'^[♪*●•▪]', stripped):
                continue
            upper = core.isupper() and len(core) > 1
            digit = any(ch.isdigit() for ch in core)
            if (upper or digit) and not core[-1].islower():
                continue
            started = True
            out.append(t)
        else:
            out.append(t)
    return ' '.join(out).strip()


def load_segment_starts(book_id):
    """Start times of the paragraph-level Whisper segments (sentence boundaries)."""
    path = os.path.join(SEG_ROOT, book_id + '.json')
    if not os.path.exists(path):
        return []
    data = json.load(open(path, encoding='utf-8'))
    return [int(seg['offsets']['from']) for seg in data.get('transcription', [])
            if seg.get('text', '').strip()]


def rebuild(book_id, zh_source=None):
    data_path = os.path.join(TEXT_ROOT, book_id + '.json')
    data = json.load(open(data_path, encoding='utf-8'))
    raw_tokens = load_raw_tokens(book_id)
    if not raw_tokens:
        print(book_id, 'no word transcript')
        return
    min_time = story_min_time(book_id, raw_tokens)

    # Transcript words (story part only).
    trans_words = []
    for w, start, end, raw in raw_tokens:
        if start < min_time:
            continue
        trans_words.append((w, start, end))
    if not trans_words:
        print(book_id, 'no story words')
        return

    # Transcript sentences: split on punctuation and long pauses.
    trans_sentences = []
    current = []
    prev_end = None
    for w, start, end in trans_words:
        if prev_end is not None and start - prev_end > 800 and current:
            trans_sentences.append(current)
            current = []
        current.append((w, start, end))
        prev_end = end
    # We need punctuation, which is in the raw token text; reload pairing.
    # Rebuild with raw text by index.
    raw_story = []
    for w, start, end, raw in raw_tokens:
        if start < min_time:
            continue
        raw_story.append(raw.strip())
    groups = []
    current = []
    prev_end = None
    seg_starts = load_segment_starts(book_id)
    for i, (w, start, end) in enumerate(trans_words):
        raw = raw_story[i] if i < len(raw_story) else ''
        prev_raw = raw_story[i - 1] if i > 0 else ''
        if prev_end is not None and start - prev_end > 800 and current:
            groups.append(current)
            current = []
        elif (current and prev_raw.endswith(',') and current[-1][3] < end
              and any(abs(start - s) <= 20 for s in seg_starts)):
            # Comma at a paragraph-segment boundary: two printed sentences
            # that Whisper joined (e.g. "'Ooh!' said Kipper," / "He ran ...").
            groups.append(current)
            current = []
            prev_end = None
        current.append((i, w, start, end, raw))
        last_char = raw[-1] if raw else ''
        if last_char in '.!?"”’':
            groups.append(current)
            current = []
            prev_end = None
        else:
            prev_end = end
    if current:
        groups.append(current)

    trans_sentences = []
    for group in groups:
        if not group:
            continue
        text = fix_asr(' '.join(g[4].strip() for g in group))
        text = strip_intro_tail(text)
        words = [norm(t) for t in re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*", text)]
        words = [w for w in words if w]
        if not words:
            continue
        lead = next((g for g in group if g[1]), group[0])
        start = max(0, lead[2] - 40)
        end = group[-1][3] + 60
        if end <= start:
            end = start + 200
        trans_sentences.append({'text': text, 'norm': words,
                                'start': start, 'end': end,
                                'w_start': group[0][0], 'w_end': group[-1][0]})
    trans_sentences = [s for s in trans_sentences if not is_tail_meta(s['text'])]
    if not trans_sentences:
        print(book_id, 'no transcript sentences')
        return

    # OCR pages (original page mapping).
    ocr_pages = load_ocr_pages(book_id)

    # Flat OCR word list in page order.
    ocr_words_flat = []   # (norm, page_index, ocr_sentence_index)
    ocr_sentence_refs = []  # (page, sentence_index) per OCR sentence
    for pi, ocrs in enumerate(ocr_pages):
        for oi, o in enumerate(ocrs):
            ocr_sentence_refs.append((pi, oi, o['en'], o['zh']))
            for w in o['words']:
                ocr_words_flat.append((w, pi, oi))

    pages = data['pages']

    # Assign transcript sentences to pages. The narrator reads page by page,
    # so narration order IS page order: distribute the transcript sentences
    # across the printed pages proportionally to each page's sentence count.
    # Front/back matter pages (parents' notes, activities) never receive
    # story text.
    FRONT_MARKERS = [
        "what's this story about", 'whats this story about', 'talk together',
        'read the story', 'word recognition', 'language comprehension',
        'written by', 'illustrated by', 'oxford reading tree',
        'this story practises', 'play a game', 'find the word', 'book band',
        'guided reading', 'activities', 'before reading', 'after reading',
        'ask the child', 'the children should',
    ]
    assigned = [[] for _ in pages]
    printed_counts = []
    for pi in range(len(pages)):
        ocrs = ocr_pages[pi]
        low = ' '.join(o['en'] for o in ocrs).lower()
        is_front = any(m in low for m in FRONT_MARKERS)
        printed_counts.append(0 if is_front else len(ocrs))
    text_pages = [pi for pi, c in enumerate(printed_counts) if c > 0]
    M = len(trans_sentences)
    if text_pages and M:
        total_printed = sum(printed_counts[pi] for pi in text_pages)
        cum = 0
        prev_j = 0
        for k, pi in enumerate(text_pages):
            cum += printed_counts[pi]
            j_end = M if k == len(text_pages) - 1 else int(round(M * cum / total_printed))
            j_end = min(M, max(j_end, prev_j + 1))
            for j in range(prev_j, j_end):
                assigned[pi].append(j)
            prev_j = j_end

    # Cohesion: an attribution fragment ("Said Chip.") belongs with the
    # dialogue it follows, even when the proportional boundary split them
    # across two pages.
    ATTR_WORDS = {'said', 'asked', 'called', 'shouted', 'cried', 'laughed',
                  'whispered', 'replied', 'answered', 'groaned', 'moaned',
                  'yelled', 'wailed', 'sniffed'}
    page_of = {}
    for pi2, items in enumerate(assigned):
        for j in items:
            page_of[j] = pi2
    for j in range(1, M):
        t = trans_sentences[j]
        if not t['norm'] or t['norm'][0] not in ATTR_WORDS:
            continue
        prev_page = page_of.get(j - 1)
        if prev_page is not None and page_of.get(j) != prev_page:
            assigned[page_of[j]].remove(j)
            assigned[prev_page].append(j)
            page_of[j] = prev_page

    # Boundary correction: compare the first transcript sentence of page B
    # with the last printed line of page A; if it clearly belongs to A's
    # print, move it back (and vice versa).
    for k in range(len(text_pages) - 1):
        pa, pb = text_pages[k], text_pages[k + 1]
        if not assigned[pa] or not assigned[pb]:
            continue
        j_first = min(assigned[pb])
        j_last = max(assigned[pa])
        if j_last > j_first:
            continue
        t = trans_sentences[j_first]
        # Compare with the last two printed lines of A (attribution lines
        # often follow the dialogue line) and the first printed line of B.
        a_lines = ocr_pages[pa][-2:] if ocr_pages[pa] else []
        first_b = ocr_pages[pb][0] if ocr_pages[pb] else None
        if not a_lines or not first_b:
            continue
        sims_a = [difflib.SequenceMatcher(None, t['norm'], line['words']).ratio()
                  for line in a_lines]
        sim_b = difflib.SequenceMatcher(None, t['norm'], first_b['words']).ratio()
        end_a = trans_sentences[j_last]['end']
        # Time guard: only pull back when the sentence starts inside page A's
        # audio span (repeated similar lines on different pages are told
        # apart by where they are spoken). If page A is under-filled (fewer
        # sentences than printed lines), trust the text match instead.
        time_ok = t['start'] < end_a or len(assigned[pa]) < len(ocr_pages[pa])
        # A short dialogue fragment followed by its attribution ("Don't be
        # silly," / "Said Wilf.") is compared as one pair. Sentences that
        # already carry their attribution are handled by the single rule.
        frag = re.search(r'\b[Ss]aid\b|\b[Aa]sked\b|\b[Cc]alled\b|\b[Ss]houted\b',
                         t['text'])
        pair_norm = list(t['norm'])
        j_next = j_first + 1
        eligible = len(pair_norm) <= 4 and not (
            frag and frag.end() >= len(t['text'].strip()) - 3)
        if eligible and j_next in assigned[pb] \
                and trans_sentences[j_next]['norm'] \
                and trans_sentences[j_next]['norm'][0] in ATTR_WORDS:
            pair_norm += trans_sentences[j_next]['norm']
        if time_ok and len(pair_norm) > len(t['norm']):
            pair_sims = [difflib.SequenceMatcher(None, pair_norm, line['words']).ratio()
                         for line in a_lines]
            pair_simb = difflib.SequenceMatcher(None, pair_norm, first_b['words']).ratio()
            if max(pair_sims) >= 0.55 and max(pair_sims) > pair_simb + 0.05:
                assigned[pb].remove(j_first)
                assigned[pb].remove(j_next)
                assigned[pa].append(j_first)
                assigned[pa].append(j_next)
                continue
        if time_ok and max(sims_a) >= 0.65 and max(sims_a) > sim_b + 0.05:
            assigned[pb].remove(j_first)
            assigned[pa].append(j_first)
            continue
        # Reverse check: the last sentence of A may belong to B's first line.
        t2 = trans_sentences[j_last]
        sim_a2 = difflib.SequenceMatcher(None, t2['norm'], a_lines[-1]['words']).ratio()
        sim_b2 = difflib.SequenceMatcher(None, t2['norm'], first_b['words']).ratio()
        if sim_b2 >= 0.65 and sim_b2 > sim_a2 + 0.05 \
                and t2['start'] < trans_sentences[j_first]['start']:
            assigned[pa].remove(j_last)
            assigned[pb].append(j_last)
            continue
        # Forward move: a trailing sentence of A that was spoken after B's
        # narration began belongs to page B (proportional drift).
        if t2['start'] > trans_sentences[j_first]['start'] + 500:
            assigned[pa].remove(j_last)
            assigned[pb].append(j_last)

    # Resolve each sentence's printed text (with cross-page rescue).
    flat_ocr = [(pi, oi, o) for pi, ocrs in enumerate(ocr_pages)
                for oi, o in enumerate(ocrs)]
    ocr_used = set()  # (page, index) of OCR sentences already claimed
    page_of_j = {}
    for pgi, items in enumerate(assigned):
        for j in items:
            page_of_j[j] = pgi
    resolved = [[] for _ in pages]  # final page -> (index, sentence dict)
    for pi in range(len(pages)):
        for si in sorted(assigned[pi]):
            t = trans_sentences[si]
            en = None
            target = pi
            match = None  # (page, index, ocr dict)
            best = None
            for oi, o in enumerate(ocr_pages[pi]):
                sim = difflib.SequenceMatcher(None, o['words'], t['norm']).ratio()
                if best is None or sim > best[0]:
                    best = (sim, oi, o)
            if best and best[0] >= 0.85:
                en = best[2]['en']
                match = (pi, best[1], best[2])
            else:
                gbest = None
                for gp, gidx, o in flat_ocr:
                    sim = difflib.SequenceMatcher(None, o['words'], t['norm']).ratio()
                    if gbest is None or sim > gbest[0]:
                        gbest = (sim, gp, gidx, o)
                # Time guard for moving the sentence to another page: never
                # jump backward past the previous sentence's speech.
                def rescue_target(gp):
                    prev_j = si - 1
                    if gp < pi:
                        pp = page_of_j.get(prev_j)
                        if pp is not None and pp > gp:
                            return pi
                        if pp == pi and t['start'] > trans_sentences[prev_j]['end']:
                            return pi
                    return gp
                if gbest and gbest[0] >= 0.88 and abs(gbest[1] - pi) <= 1 \
                        and len(t['norm']) >= 3:
                    en = gbest[3]['en']
                    match = (gbest[1], gbest[2], gbest[3])
                    target = rescue_target(gbest[1])
                elif gbest and gbest[0] >= 0.72 and abs(gbest[1] - pi) <= 1 \
                        and len(t['norm']) >= 2 \
                        and set(t['norm']) <= set(gbest[3]['words']) \
                        and len(gbest[3]['words']) - len(t['norm']) <= 3:
                    # The narrator read the printed sentence but Whisper missed
                    # a word or two; the printed text contains every word.
                    en = gbest[3]['en']
                    match = (gbest[1], gbest[2], gbest[3])
                    target = rescue_target(gbest[1])
            if not en:
                en = t['text']
            if match and (match[0], match[1]) in ocr_used:
                match = None
            if match:
                ocr_used.add((match[0], match[1]))
                # A lowercase continuation ("said Kipper.") often belongs to a
                # short interjection on the same page ("'Ooh!' said Kipper.").
                if en[:1].islower() and match[1] > 0:
                    prev = ocr_pages[match[0]][match[1] - 1]
                    if (match[0], match[1] - 1) not in ocr_used \
                            and len(prev['words']) <= 2:
                        ocr_used.add((match[0], match[1] - 1))
                        en = prev['en'] + ' ' + en
                        t['norm'] = t['norm'] + [w for w in prev['words']
                                                 if w not in t['norm']]
            if en and en[:1].isalpha() and not en.startswith(("'", '"')):
                en = en[0].upper() + en[1:]
            en = clean_display_en(en)
            zh = best_zh(t['norm'], zh_source)
            resolved[target].append((si, {'en': en, 'zh': zh,
                                          'startMs': t['start'], 'endMs': t['end']}))

    # Build final page data.
    for pi, page in enumerate(pages):
        final = [item for _, item in sorted(resolved[pi], key=lambda x: x[1]['startMs'])]
        if final:
            page['sentences'] = final
            page['startMs'] = max(0, min(f['startMs'] for f in final) - 150)
            page['endMs'] = max(f['endMs'] for f in final) + 350
            page.pop('illustrationOnly', None)
        else:
            page['sentences'] = []
            page['startMs'] = 0
            page['endMs'] = 0
    json.dump(data, open(data_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    total = sum(len(p['sentences']) for p in pages)
    first = min((s['startMs'] for p in pages for s in p['sentences']), default=0)
    text_pages = sum(1 for p in pages if p['sentences'])
    print(book_id, 'sentences:', total, 'text_pages:', text_pages,
          'story_start:', first)


def load_zh_source(level):
    out = []
    for src in [f'/tmp/text_before_rebuild3/L{level}-*.json',
                f'/tmp/text_before_rebuild2/L{level}-*.json',
                f'/tmp/text_before_rebuild/L{level}-*.json']:
        for path in glob.glob(src):
            d = json.load(open(path, encoding='utf-8'))
            for page in d['pages']:
                for s in page.get('sentences', []):
                    en = s.get('en', '').strip()
                    zh = s.get('zh', '').strip()
                    if en and zh:
                        out.append((norm(en), zh))
    cache = '/tmp/l5_translations.json' if level == '5' else '/tmp/all_translations.json'
    if os.path.exists(cache):
        d = json.load(open(cache, encoding='utf-8'))
        for en, zh in d.items():
            if zh:
                out.append((norm(en), zh))
    return out


def main():
    levels = sys.argv[1:] or ['5', '6']
    for level in levels:
        zh_source = load_zh_source(level)
        for path in sorted(glob.glob(os.path.join(TEXT_ROOT, f'L{level}-*.json'))):
            book_id = os.path.splitext(os.path.basename(path))[0]
            rebuild(book_id, zh_source)


if __name__ == '__main__':
    main()
