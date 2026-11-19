import json, glob, re, os, sys
from collections import Counter

ROOT = 'app/src/main/assets/oxford/text'
WEB2 = set()
with open('/usr/share/dict/web2', 'r', errors='ignore') as f:
    for line in f:
        w = line.strip().lower()
        if w:
            WEB2.add(w)

NAMES = set('''biff kipper chip wilf wilma floppy nadim anneena buster lee rosie ellie gran grandma grandpa mum dad mrs mr ms dr omar adeel tiger cairo zak martha seabay honey johnson may byrne mary annie joe jack tom sam ben max molly lilly milly billy danny sunny bunny dog dogs cat cats'''.split())
CONTRACTIONS = set('''don't can't didn't couldn't won't isn't aren't wasn't weren't doesn't hasn't haven't hadn't wouldn't shouldn't it's i'm i've i'll i'd you're you've you'll you'd he's he'd she's she'd we're we've we'll we'd they're they've they'll they'd that's that'll there's there'll here's what's what'll who's who'll where's when's why's how's let's mustn't needn't shan't could've should've would've might've'''.split())

FRONT_MATTER = [
    "talk together", "what's this story about", "what’s this story about",
    "word recognition", "language comprehension", "story written by",
    "read the story", "before reading", "after reading", "book band",
    "this story practises", "this story practices", "available in packs",
    "isbn", "class pack", "teaching notes", "oxford university press",
    "series created by", "illustrated by"
]
SERIES_PHRASES = [
    "Oxford Reading Tree", "oxford reading tree", "First Sentences",
    "first sentences", "More Patterned Stories", "More First Sentences",
    "Roderick Hunt", "Alex Brychta", "Stage 1+", "Stage 2", "Stage 3",
    "Stage 4", "Stage 5", "Stage 6", "Stage 7", "Stage 8", "Stage 9"
]

def stem_candidates(word):
    w = word.lower().replace('’', "'")
    out = []
    if w in CONTRACTIONS:
        return [w]
    base = w
    if base.endswith("'s"):
        base = base[:-2]
    out.append(base)
    if base.endswith('ies') and len(base) > 4:
        out.append(base[:-3] + 'y')
    if base.endswith('es') and len(base) > 3:
        out.append(base[:-2])
    if base.endswith('s') and len(base) > 2:
        out.append(base[:-1])
    if base.endswith('ed') and len(base) > 3:
        out.append(base[:-2])
        out.append(base[:-1])
        if len(base) > 4 and base[-3] == base[-4]:
            out.append(base[:-3])
    if base.endswith('ing') and len(base) > 4:
        out.append(base[:-3])
        out.append(base[:-3] + 'e')
        if len(base) > 5 and base[-4] == base[-5]:
            out.append(base[:-4])
    if base.endswith('er') and len(base) > 3:
        out.append(base[:-2])
        out.append(base[:-1])
    if base.endswith('est') and len(base) > 4:
        out.append(base[:-3])
        out.append(base[:-2])
    if base.endswith('ly') and len(base) > 3:
        out.append(base[:-2])
    return out

def known(word):
    w = word.lower().replace('’', "'")
    if w in NAMES or w in CONTRACTIONS:
        return True
    if w.isdigit():
        return True
    if "'" in w:
        parts = re.split(r"['’]", w)
        if all(p in WEB2 or p in NAMES or p in ('s','t','re','ve','ll','d','m') for p in parts if p):
            return True
    return any(c in WEB2 or c in NAMES for c in stem_candidates(w))

def is_junk_sentence(s, word_list):
    t = s.strip()
    if not t:
        return True
    if len(t) < 2:
        return True
    if len(t) > 300:
        return True
    lower = t.lower()
    if any(p.lower() in lower for p in SERIES_PHRASES):
        return True
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return True
    if letters and all(c.isupper() for c in letters) and len(word_list) > 2:
        return True
    # A line that is mostly digits / punctuation.
    if sum(c.isalpha() for c in t) < len(t) * 0.35:
        return True
    # Drop obvious packaging / label noise.
    if re.match(r'^(ISBN|Book Band)\b', t, re.I):
        return True
    if re.search(r'\b(ISBN|Class Pack|Teaching Notes)\b', t, re.I):
        return True
    # For multi-word sentences, require some dictionary coverage.
    if len(word_list) >= 3:
        good = sum(1 for w in word_list if known(w))
        if good / len(word_list) < 0.45:
            return True
    if len(word_list) == 1 and not known(word_list[0]):
        # Keep short exclamations and names, drop random OCR fragments.
        w = word_list[0].lower()
        if w not in ('oh','ah','hey','hi','hello','yes','no','wow','help','run','go','stop','look','come','mum','dad'):
            return True
    return False

all_words = Counter()
changed = 0
for path in sorted(glob.glob(os.path.join(ROOT, '*.json'))):
    with open(path) as f:
        data = json.load(f)
    pages = data['pages']
    new_pages = []
    for idx, page in enumerate(pages):
        sentences = []
        # Covers and front/back matter are not story pages.
        if idx == 0:
            page_sentences = []
        else:
            page_sentences = [s['en'] for s in page.get('sentences', [])]
            joined = ' '.join(page_sentences).lower()
            if any(k in joined for k in FRONT_MATTER):
                page_sentences = []
        for text in page_sentences:
            # Remove series phrases that may be embedded in a line.
            for phrase in SERIES_PHRASES:
                text = re.sub(re.escape(phrase), ' ', text, flags=re.I)
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                continue
            words = re.findall(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", text)
            if is_junk_sentence(text, words):
                continue
            sentences.append({'en': text})
            for w in words:
                all_words[w.lower().replace('’', "'")] += 1
        new_pages.append({'sentences': sentences})
    data['pages'] = new_pages
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    changed += 1

with open('/tmp/oxford_words_clean.json', 'w') as f:
    json.dump(dict(sorted(all_words.items())), f, ensure_ascii=False, indent=2)
print('cleaned books', changed, 'unique words', len(all_words))
print('total sentences', sum(1 for p in glob.glob(os.path.join(ROOT,'*.json')) for pg in json.load(open(p))['pages'] for s in pg['sentences']))
