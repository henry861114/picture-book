import json, glob, re, os
from collections import Counter

ROOT = 'app/src/main/assets/oxford/text'
STARTERS = set('''The A An He She It They We I You Mum Dad Biff Chip Kipper Wilf Wilma Floppy Nadim Anneena Everyone Mr Mrs Miss Gran Grandpa Grandma Suddenly Then One Some His Her Their My Our Your This That These Those There Here What Where When Why How Who Can Could Will Would Do Did Does Is Are Was Were Have Has Had Let Look Come Go Stop Help Oh No Yes At In On Up Down Out Into After Before Later Soon First Next Finally Somebody Nobody Something Nothing'''.split())
WEB2 = set()
with open('/usr/share/dict/web2', errors='ignore') as f:
    for line in f:
        w=line.strip().lower()
        if w: WEB2.add(w)
NAMES = set('''biff kipper chip wilf wilma floppy nadim anneena buster lee rosie ellie gran grandma grandpa mum dad mrs mr ms dr omar adeel tiger cairo zak martha seabay honey johnson may byrne'''.split())

def word_matches(text):
    return list(re.finditer(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", text))

def strip_prefix(text):
    ms = word_matches(text)
    if not ms: return text
    if ms[0].group(0) in STARTERS: return text
    for i, m in enumerate(ms[1:], 1):
        if m.group(0) in STARTERS and len(ms) - i >= 2:
            return text[m.start():].strip()
    return text

def uppercase_ratio(text):
    ms = word_matches(text)
    if not ms: return 0
    return sum(1 for m in ms if m.group(0)[0].isupper()) / len(ms)

def known(w):
    w=w.lower().replace('’',"'")
    if w in NAMES: return True
    if "'" in w:
        parts=re.split(r"['’]",w)
        if all(p in WEB2 or p in NAMES or p in ('s','t','re','ve','ll','d','m') for p in parts if p): return True
    if w in WEB2: return True
    # simple stems
    for suf, rep in [('ies','y'),('es',''),('s',''),('ed',''),('ed','e'),('ing',''),('ing','e'),('er',''),('est','')]:
        if w.endswith(suf) and len(w)>len(suf)+2:
            c=w[:-len(suf)]+rep
            if c in WEB2: return True
    return False

all_words=Counter()
removed=0
for path in sorted(glob.glob(os.path.join(ROOT,'*.json'))):
    d=json.load(open(path))
    for page in d['pages']:
        new=[]
        for s in page['sentences']:
            t=strip_prefix(s['en'])
            t=re.sub(r'\s+',' ',t).strip()
            if not t: continue
            ms=word_matches(t)
            # Drop label-like lines, but keep real sentences with names such as
            # "No, it's Dad." or "Biff and Chip.".
            if len(ms) >= 3 and all(m.group(0)[0].isupper() for m in ms):
                removed += 1
                continue
            if len(ms) >= 4 and uppercase_ratio(t) >= 0.85:
                removed += 1
                continue
            # Drop sentences that begin with a determiner/pronoun but have no verb-like word and are mostly unknown.
            if len(ms)>=3:
                good=sum(1 for m in ms if known(m.group(0)))
                if good/len(ms) < 0.5:
                    removed+=1; continue
            new.append({'en':t})
            for m in ms:
                all_words[m.group(0).lower().replace('’',"'")]+=1
        page['sentences']=new
    json.dump(d, open(path,'w'), ensure_ascii=False, indent=2)
json.dump(dict(sorted(all_words.items())), open('/tmp/oxford_words_clean2.json','w'), ensure_ascii=False, indent=2)
print('removed',removed,'unique words',len(all_words),'sentences',sum(1 for p in glob.glob(os.path.join(ROOT,'*.json')) for pg in json.load(open(p))['pages'] for s in pg['sentences']))
