import json, glob, re, os
from collections import Counter
ROOT='app/src/main/assets/oxford/text'
all_words=Counter(); removed=0; merged=0
for path in sorted(glob.glob(os.path.join(ROOT,'*.json'))):
    d=json.load(open(path))
    for page in d['pages']:
        new=[]
        for s in page['sentences']:
            t=s['en'].strip()
            if not t: continue
            letters=[c for c in t if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                removed+=1; continue
            if t[0].islower() and new:
                new[-1]['en'] = new[-1]['en'].rstrip() + ' ' + t
                merged+=1
            else:
                new.append({'en':t})
        page['sentences']=new
        for s in new:
            for m in re.finditer(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", s['en']):
                all_words[m.group(0).lower().replace('’',"'")]+=1
    json.dump(d, open(path,'w'), ensure_ascii=False, indent=2)
json.dump(dict(sorted(all_words.items())), open('/tmp/oxford_words_clean3.json','w'), ensure_ascii=False, indent=2)
print('removed',removed,'merged',merged,'unique',len(all_words),'sentences',sum(1 for p in glob.glob(os.path.join(ROOT,'*.json')) for pg in json.load(open(p))['pages'] for s in pg['sentences']))
