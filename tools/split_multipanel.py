#!/usr/bin/env python3
"""Split multi-panel PDF pages into individual story pages (data pipeline).

Some Oxford PDFs (the "Lesson N" educational editions) hold 2-3 scanned
story pages on one PDF page. This tool:

1. renders each PDF page and detects the story-page panels
   (recursive row/column gap analysis, same rules as the reader had);
2. OCRs each panel with macOS Vision;
3. assigns the narration sentences to panels with a monotonic
   dynamic-programming alignment on word similarity;
4. rewrites the text JSON: one page entry per panel with its crop rect
   ("pdfPage" + "rect") and its sentences;
5. updates library.json page counts.

The reader renders each entry by cropping the PDF page to the rect.
"""
import difflib
import glob
import json
import os
import re
import subprocess
import sys

import pypdfium2 as pdfium

ASSETS = 'app/src/main/assets/oxford'
LEVELS = sys.argv[1:] or ['5', '6', '7', '8', '9']
TMP = '/tmp/panel_ocr'
os.makedirs(TMP, exist_ok=True)


def norm_words(text):
    text = (text or '').lower().replace('\u2019', "'")
    return [w for w in re.sub(r"[^a-z0-9' ]", ' ', text).split() if w]


def is_frame_blue(px, w, h):
    def blue(x, y):
        r, g, b = px[x, y]
        return b > 130 and b > r * 1.6 and b > g * 1.4 and r < 130 and g < 130
    return (blue(2, 2) and blue(w - 3, 2) and blue(2, h - 3)
            and blue(w - 3, h - 3))


def crop_blue_frame(img):
    px = img.load()
    w, h = img.size
    if not is_frame_blue(px, w, h):
        return img
    step = max(1, min(w, h) // 120)
    left, top, right, bottom = w, h, -1, -1
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if not (b > 100 and b > r * 1.3 and b > g * 1.15
                    and r < 140 and g < 140):
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y
    if right <= left or bottom <= top:
        return img
    pad = max(4, min(w, h) // 90)
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w - 1, right + pad)
    bottom = min(h - 1, bottom + pad)
    return img.crop((left, top, right + 1, bottom + 1))


def detect_panels(img):
    """Recursive panel detection; returns rects in 0..1 fractions."""
    px = img.load()
    w, h = img.size
    leaves = []

    def profile(a0, a1, c0, c1, horizontal):
        out = []
        step = max(1, (c1 - c0) // 60)
        for a in range(a0, a1):
            hit = 0
            cnt = 0
            for c in range(c0, c1, step):
                cnt += 1
                p = px[c, a] if horizontal else px[a, c]
                if p[0] < 240 or p[1] < 240 or p[2] < 240:
                    hit += 1
            out.append(hit / cnt if cnt else 0.0)
        return out

    def bands(a0, a1, c0, c1, horizontal):
        prof = profile(a0, a1, c0, c1, horizontal)
        out = []
        min_gap = max(2, round((a1 - a0) * 0.03))
        run = None
        for i, a in enumerate(range(a0, a1)):
            empty = prof[i] < 0.02
            if empty and run is None:
                run = a
            if not empty and run is not None:
                if a - run >= min_gap:
                    out.append((run, a))
                run = None
        if run is not None and a1 - run >= min_gap:
            out.append((run, a1))
        return out

    def segments(frm, to, bs, total):
        segs = []
        top = frm
        for b in bs:
            mid = (b[0] + b[1]) // 2
            if mid - top >= total * 0.06:
                segs.append((top, mid))
            top = mid
        if to - top >= total * 0.06:
            segs.append((top, to))
        return segs

    def split(l, t, r, b, depth):
        x0, x1 = round(l * w), max(round(l * w) + 1, round(r * w))
        y0, y1 = round(t * h), max(round(t * h) + 1, round(b * h))
        if x1 - x0 < 60 or y1 - y0 < 60 or depth > 3:
            leaves.append((l, t, r, b))
            return
        row_bands = bands(y0, y1, x0, x1, True)
        if os.environ.get('DBG2'):
            print('DBG2 row bands:', row_bands, 'col bands:', bands(x0, x1, y0, y1, False))
        row_segs = segments(y0, y1, row_bands, h)
        if len(row_segs) >= 2:
            for a, bb in row_segs:
                split(l, a / h, r, bb / h, depth + 1)
            return
        col_bands = bands(x0, x1, y0, y1, False)
        col_segs = segments(x0, x1, col_bands, w)
        if len(col_segs) >= 2:
            for a, bb in col_segs:
                split(a / w, t, bb / w, b, depth + 1)
            return
        if r - l > (b - t) * 1.6 and (b - t) >= 0.28 and depth < 3:
            best_x, best_c = None, 1.0
            for x in range(int(w * 0.3), int(w * 0.7) + 1):
                hit = 0
                cnt = 0
                for y in range(y0 + 2, y1 - 2):
                    cnt += 1
                    p = px[x, y]
                    if p[0] < 245 or p[1] < 245 or p[2] < 245:
                        hit += 1
                frac = hit / cnt if cnt else 1.0
                if frac < best_c:
                    best_c = frac
                    best_x = x
            if best_x is not None and best_c < 0.45:
                mid = best_x / w
                split(l, t, mid, b, depth + 1)
                split(mid, t, r, b, depth + 1)
                return
            # Fallback: a Lesson-edition spread holds equal-width pages;
            # split at the midpoint even when the pages touch.
            if best_x is not None and (r - l) / (b - t) < 3.0:
                mid = (l + r) / 2
                split(l, t, mid, b, depth + 1)
                split(mid, t, r, b, depth + 1)
                return
        leaves.append((l, t, r, b))

    split(0.0, 0.0, 1.0, 1.0, 0)
    if os.environ.get('DBG'):
        print('DBG leaves:', [[round(v,2) for v in x] for x in leaves])
    if len(leaves) <= 1:
        return [(0.0, 0.0, 1.0, 1.0)]

    # Merge small rectangles (headers, titles, captions) into the picture
    # sharing their column.
    merged = []
    for leaf in leaves:
        lh = leaf[3] - leaf[1]
        if merged and lh < 0.30:
            prev = merged[-1]
            overlap = min(prev[2], leaf[2]) - max(prev[0], leaf[0])
            same_col = overlap > 0.8 * min(prev[2] - prev[0],
                                           leaf[2] - leaf[0])
            fits = (prev[3] - prev[1]) + lh <= 0.55
            if same_col and fits:
                prev[0] = min(prev[0], leaf[0])
                prev[1] = min(prev[1], leaf[1])
                prev[2] = max(prev[2], leaf[2])
                prev[3] = max(prev[3], leaf[3])
                continue
        merged.append(list(leaf))
    if os.environ.get('DBG'):
        print('DBG merged:', [[round(v,2) for v in x] for x in merged])
    if len(merged) <= 1:
        return [(0.0, 0.0, 1.0, 1.0)]

    # Drop tiny panels (page numbers, price tags).
    merged = [p for p in merged
              if (p[2] - p[0]) * (p[3] - p[1]) >= 0.004]
    if len(merged) <= 1:
        return [(0.0, 0.0, 1.0, 1.0)]
    # Drop panels fully contained in another (detection fragments).
    cleaned = []
    for panel in merged:
        contained = False
        for other in merged:
            if other is panel:
                continue
            if (other[0] <= panel[0] + 0.01 and other[1] <= panel[1] + 0.01
                    and other[2] >= panel[2] - 0.01
                    and other[3] >= panel[3] - 0.01):
                contained = True
                break
        if not contained:
            cleaned.append(panel)
    merged = cleaned
    # Validation: every panel must be portrait like a story page.
    page_aspect = h / w
    for panel in merged:
        pw = panel[2] - panel[0]
        ph = (panel[3] - panel[1]) * page_aspect
        if pw <= 0.02 or ph / max(pw, 1e-6) < 0.5:
            return [(0.0, 0.0, 1.0, 1.0)]
    return merged


def ocr_image(path):
    import Vision as V
    from Foundation import NSURL
    req = V.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
    handler = V.VNImageRequestHandler.alloc().initWithURL_options_(
        NSURL.fileURLWithPath_(path), None)
    handler.performRequests_error_([req], None)
    lines = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if cand:
            lines.append(cand[0].string())
    return ' '.join(lines)


def ocr_panel(pdf_path, page_index, rect, tag):
    scale = 900 / 595.0  # ~900 px wide for letter-ish pages; refined below
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[page_index]
    w_pt, h_pt = page.get_size()
    scale = 1400 / max(w_pt, 1)
    img = page.render(scale=scale).to_pil().convert('RGB')
    w, h = img.size
    l, t, r, b = rect
    crop = img.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
    path = os.path.join(TMP, tag + '.png')
    crop.save(path)
    text = ocr_image(path)
    return text


def assign(sentences, panel_texts):
    """Monotonic DP: assign each sentence to a panel (panels may be empty)."""
    n, k = len(sentences), len(panel_texts)
    if n == 0 or k == 0:
        return [0] * n
    sw = [norm_words(s.get('en', '')) for s in sentences]
    pw = [norm_words(t) for t in panel_texts]
    ratio = {}
    for i in range(n):
        for j in range(k):
            if not sw[i] or not pw[j]:
                ratio[(i, j)] = 0.0
                continue
            ratio[(i, j)] = difflib.SequenceMatcher(None, sw[i], pw[j]).ratio()
    NEG = -1e9
    # f[i][j]: best score for first i sentences over first j panels.
    f = [[NEG] * (k + 1) for _ in range(n + 1)]
    take = [[0] * (k + 1) for _ in range(n + 1)]  # sentences used by panel j-1
    for j in range(k + 1):
        f[0][j] = 0.0
    for i in range(1, n + 1):
        f[i][0] = NEG
    for i in range(1, n + 1):
        for j in range(1, k + 1):
            best = f[i][j - 1]          # panel j-1 empty
            best_t = 0
            run = 0.0
            for t in range(i, 0, -1):
                run += ratio[(t - 1, j - 1)]
                cand = f[t - 1][j - 1] + run
                if cand > best:
                    best = cand
                    best_t = i - t + 1
            f[i][j] = best
            take[i][j] = best_t
    # Backtrack.
    assignment = [0] * n
    i, j = n, k
    while i > 0 and j > 0:
        t = take[i][j]
        for u in range(i - t, i):
            assignment[u] = j - 1
        i -= t
        j -= 1
    return assignment


def white_gutters(img, axis, min_h=0.012, edge=0.03, thr=230, frac=0.985):
    """Centers of blank full-length bands of the scan (panel gutters).

    axis 'y' scans pixel rows (horizontal gutters), 'x' scans columns.
    Only interior bands at least min_h of the page are returned.
    """
    w, h = img.size
    n, span = (h, w) if axis == 'y' else (w, h)
    px = img.load()
    step = max(1, span // 240)
    prof = []
    for k in range(n):
        cnt = tot = 0
        for t in range(0, span, step):
            p = px[t, k] if axis == 'y' else px[k, t]
            tot += 1
            if min(p[0], p[1], p[2]) > thr:
                cnt += 1
        prof.append(cnt / tot)
    bands = []
    cur = None
    for k in range(n):
        if prof[k] >= frac:
            if cur is None:
                cur = [k, k]
            else:
                cur[1] = k
        elif cur is not None:
            bands.append(cur)
            cur = None
    if cur is not None:
        bands.append(cur)
    out = []
    for a, b in bands:
        if (b - a + 1) / n < min_h:
            continue
        if a / n < edge or (b + 1) / n > 1.0 - edge:
            continue
        out.append(round((a + b + 1) / 2.0 / n, 4))
    return out


def band_col_gutters(img, y0, y1, thr=230, frac=0.97, min_w=0.008,
                     edge=0.02):
    """Vertical white gutters inside the horizontal band [y0,y1] of the
    page (fractions). A gutter must be (nearly) white for the WHOLE
    band — that is a real border between side-by-side panels; white sky
    inside one illustration does not qualify."""
    w, h = img.size
    px = img.load()
    a = max(0, int(y0 * h))
    b = max(a + 1, min(h, int(y1 * h)))
    step = max(1, (b - a) // 200)
    prof = []
    for k in range(w):
        cnt = tot = 0
        for t in range(a, b, step):
            q = px[k, t]
            tot += 1
            if min(q[0], q[1], q[2]) > thr:
                cnt += 1
        prof.append(cnt / tot)
    bands = []
    cur = None
    for k in range(w):
        if prof[k] >= frac:
            if cur is None:
                cur = [k, k]
            else:
                cur[1] = k
        elif cur is not None:
            bands.append(cur)
            cur = None
    if cur is not None:
        bands.append(cur)
    out = []
    for sb, eb in bands:
        if (eb - sb + 1) / w < min_w:
            continue
        if sb / w < edge or (eb + 1) / w > 1.0 - edge:
            continue
        out.append(round((sb + eb + 1) / 2.0 / w, 4))
    return out


def band_ink(img, y0, y1, x0, x1, thr=230):
    """Fraction of non-white pixels in a rectangle of the page."""
    w, h = img.size
    px = img.load()
    a = max(0, int(y0 * h)); b = max(a + 1, min(h, int(y1 * h)))
    l = max(0, int(x0 * w)); r = max(l + 1, min(w, int(x1 * w)))
    step_y = max(1, (b - a) // 60)
    step_x = max(1, (r - l) // 60)
    cnt = tot = 0
    for t in range(a, b, step_y):
        for k in range(l, r, step_x):
            q = px[k, t]
            tot += 1
            if min(q[0], q[1], q[2]) <= thr:
                cnt += 1
    return cnt / max(1, tot)


def line_groups(lines, axis, gap=0.12):
    """Cluster OCR lines into row/column groups by center gaps."""
    def key(e):
        return (e[1] + e[3] / 2) if axis == 'y' else (e[0] + e[2] / 2)
    if not lines:
        return []
    vals = sorted(lines, key=key)
    gs, cur = [], [vals[0]]
    for e in vals[1:]:
        if key(e) - key(cur[-1]) >= gap:
            gs.append(cur)
            cur = []
        cur.append(e)
    gs.append(cur)
    return gs


def gutter_bounds(gutters, groups, axis):
    """At most ONE boundary per adjacent group pair: the white gutter
    closest BELOW the previous group's last line (a real panel border
    sits right under a caption; stray white gaps sit far from it).
    Gutters outside every pair (margins, page numbers) are dropped."""
    if len(groups) < 2:
        return []
    def key(e):
        return (e[1] + e[3] / 2) if axis == 'y' else (e[0] + e[2] / 2)
    out = []
    claimed = set()
    for a, b in zip(groups[:-1], groups[1:]):
        lo = max(key(e) for e in a)
        hi = min(key(e) for e in b)
        if hi - lo < 0.04:
            continue
        cands = [g for g in gutters if lo <= g <= hi and g not in claimed]
        if cands:
            g = min(cands, key=lambda g: g - lo)
            claimed.add(g)
            out.append(round(g, 4))
    return out


def trim_end_bands(bounds, min_band=0.12):
    """Drop end boundaries that would create a sliver first/last band
    (page numbers, footers)."""
    edges = [0.0] + list(bounds) + [1.0]
    changed = True
    while changed and len(edges) > 2:
        changed = False
        if edges[1] - edges[0] < min_band:
            del edges[1]
            changed = True
            continue
        if edges[-1] - edges[-2] < min_band:
            del edges[-2]
            changed = True
    return [round(v, 4) for v in edges[1:-1]]


def extent_bounds(groups, axis):
    """Fallback when the scan has no clean gutters (panels touch):
    split adjacent groups at the midpoint of their text extents."""
    if len(groups) < 2:
        return []
    out = []
    for a, b in zip(groups[:-1], groups[1:]):
        if axis == 'x':
            edge_a = max(e[0] + e[2] for e in a)
            edge_b = min(e[0] for e in b)
        else:
            ba = sorted(e[1] + e[3] for e in a)
            edge_a = ba[-1]
            edge_b = min(e[1] for e in b)
            if edge_b - edge_a < 0.05:
                continue
            out.append(round(edge_a + 0.01, 4))
            continue
        if edge_b - edge_a < 0.005:
            continue
        out.append(round((edge_a + edge_b) / 2, 4))
    return out


def main():
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location('po', os.path.join(here, 'panel_ocr.py'))
    po = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(po)
    spec2 = importlib.util.spec_from_file_location('abt', os.path.join(here, 'assign_by_text.py'))
    abt = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(abt)

    lib_path = os.path.join(ASSETS, 'library.json')
    lib = json.load(open(lib_path, encoding='utf-8'))
    page_counts = {}
    for level in LEVELS:
        for path in sorted(glob.glob(os.path.join(ASSETS, 'text',
                                                  f'L{level}-*.json'))):
            book_id = os.path.splitext(os.path.basename(path))[0]
            pdf_path = os.path.join(ASSETS, 'pdf', book_id + '.pdf')
            if not os.path.exists(pdf_path):
                continue
            data = json.load(open(path, encoding='utf-8'))
            pdf = pdfium.PdfDocument(pdf_path)

            # 1) Coalesce previously split pages per PDF page.
            per_pdf = {}
            order_pdf = []
            for idx, pg in enumerate(data['pages']):
                pdf_i = pg.get('pdfPage', idx)
                if pdf_i not in per_pdf:
                    per_pdf[pdf_i] = []
                    order_pdf.append(pdf_i)
                per_pdf[pdf_i] += pg.get('sentences', [])

            # 2) Merge sentence fragments globally (honorific abbreviations
            #    and sentences without terminal punctuation). The merged
            #    sequence REPLACES the per-PDF buckets — a fragment merged
            #    into its neighbour must not stay behind as a duplicate.
            flat = []
            for pdf_i in order_pdf:
                flat += [(pdf_i, s) for s in per_pdf[pdf_i]]
            merged_sents = []
            for pdf_i, s in flat:
                en = s.get('en', '').strip()
                if not en:
                    continue
                prev = merged_sents[-1][1] if merged_sents else None
                prev_en = prev['en'].strip() if prev else ''
                ends_honorific = bool(re.search(r'(?:Mrs|Mr|Dr|Ms|St)\.$', prev_en))
                ends_open = not re.search('[.!?]["\u201d\u2019\']?$', prev_en)
                # A bare attribution fragment ("Said Biff.") spoken after
                # its quote belongs to the PREVIOUS sentence: "…," said
                # Biff.  Only attach when the previous sentence does not
                # already end with an attribution.
                bare_attr = prev is not None and re.fullmatch(
                    r'[Ss]aid\s+\w+\.?', en) is not None
                already_attr = bool(
                    re.search(r'[Ss]aid\s+\w+[.,"\u201d]?$', prev_en))
                if bare_attr and not already_attr:
                    pe = prev_en.rstrip()
                    if pe.endswith('."'):
                        pe = pe[:-2] + ',"'
                    elif pe.endswith('.'):
                        pe = pe[:-1] + ','
                    prev['en'] = (pe + ' ' + en[0].lower()
                                  + en[1:]).strip()
                    prev['endMs'] = max(prev.get('endMs', 0),
                                        s.get('endMs', 0))
                    continue
                if prev and (ends_honorific or ends_open):
                    join_en = en
                    if ends_honorific:
                        # prev ends with a dangling honorific ("Said Mr.",
                        # "Mrs."); if the next sentence ALREADY starts with
                        # the same word, the fragment is an echo — drop it
                        # instead of gluing ("Mr. Mr Johnson..." ✗).
                        prev_word = re.sub(r'[^\w]', '', prev_en.split()[-1]
                                           if prev_en.split() else '').lower()
                        next_word = re.sub(r'[^\w]', '', en.split()[0]
                                           if en.split() else '').lower()
                        if prev_word and prev_word == next_word:
                            stripped = re.sub(
                                r'[\s]*' + re.escape(prev_en.split()[-1])
                                + r'\s*$', '', prev_en).strip()
                            if stripped:
                                prev['en'] = (stripped + ' ' + en).strip()
                            else:
                                prev['en'] = en
                            prev['endMs'] = max(prev.get('endMs', 0),
                                                s.get('endMs', 0))
                            continue
                    prev['en'] = (prev_en + ' ' + join_en).strip()
                    prev['endMs'] = max(prev.get('endMs', 0),
                                        s.get('endMs', 0))
                    continue
                merged_sents.append((pdf_i, s))
            per_pdf = {i: [] for i in order_pdf}
            for pdf_i, s in merged_sents:
                per_pdf[pdf_i].append(s)

            # 3) Book-level Lesson gate.
            lesson_edition = False
            for probe_i in range(min(3, len(pdf))):
                probe = pdf[probe_i].render(scale=900 / 595.0).to_pil().convert('RGB')
                probe_path = os.path.join(TMP, f'{book_id}_bp{probe_i}.png')
                probe.save(probe_path)
                if re.search(r'lesson\s*\d+', ocr_image(probe_path), re.I):
                    lesson_edition = True
                    break

            # 4) Panels per PDF page + OCR text; global panel sequence.
            panels = []       # (pdf_i, rect)
            panel_texts = []  # OCR text per panel
            new_pages = []
            carry = []            # narration handed over to the next page
            for i in order_pdf:
                sents_i = carry + per_pdf[i]
                carry = []
                if os.environ.get('DBGD5'):
                    print(f'DBGD5 {book_id} pdf{i}: sents={len(sents_i)} '
                          f'lesson={lesson_edition}', flush=True)
                if not lesson_edition or not sents_i:
                    panels.append((i, None))
                    panel_texts.append('')
                    entry = {'sentences': sents_i, 'pdfPage': i}
                    if sents_i:
                        entry['startMs'] = max(0, min(s['startMs']
                                                      for s in sents_i) - 150)
                        entry['endMs'] = max(s['endMs'] for s in sents_i) + 350
                    else:
                        entry['startMs'] = 0
                        entry['endMs'] = 0
                    new_pages.append(entry)
                    continue
                # Grid detection: panel borders are the WHITE gutters of
                # the scan (blank full-width bands between tiled story
                # pages). Text-center heuristics misjudge these: captions
                # of neighbouring columns can share a baseline, and
                # lettering inside illustrations pollutes the OCR.
                img_hi = pdf[i].render(scale=900 / 595.0).to_pil().convert('RGB')
                hi_path = os.path.join(TMP, f'{book_id}_det{i}.png')
                img_hi.save(hi_path)
                ocr_lines = po.ocr_lines(hi_path)
                # Normalize to (x, y_top-down, w, h, text). Vision reports
                # the line BOTTOM in bottom-up coords: top-down top = 1-y.
                ocr_lines = [(e[1], 1.0 - e[2], e[3], e[4], e[0])
                             for e in ocr_lines]
                if not ocr_lines:
                    entry = dict(text_page)
                    entry['pdfPage'] = i
                    entry.pop('rect', None)
                    new_pages.append(entry)
                    continue
                y_gutters = white_gutters(img_hi, 'y')
                x_gutters = white_gutters(img_hi, 'x')
                # Structure lines: drop 1-word OCR hits (page numbers,
                # badges) that would create junk groups.
                struct = [e for e in ocr_lines if len(e[4].split()) >= 2]
                y_groups = line_groups(struct, 'y')
                x_groups = line_groups(struct, 'x')
                y_bounds = gutter_bounds(y_gutters, y_groups, 'y')
                if not y_bounds and len(y_groups) >= 2 and y_gutters:
                    y_bounds = trim_end_bands(y_gutters)
                if not y_bounds:
                    y_bounds = extent_bounds(y_groups, 'y')
                y_bounds = trim_end_bands(y_bounds)
                x_bounds = gutter_bounds(x_gutters, x_groups, 'x')
                if not x_bounds and len(x_groups) >= 2 and x_gutters:
                    x_bounds = trim_end_bands(x_gutters)
                if not x_bounds:
                    x_bounds = extent_bounds(x_groups, 'x')
                x_bounds = trim_end_bands(x_bounds)
                if os.environ.get('DBGG2'):
                    print(f'DBGG2 {book_id} pdf{i}: yg={y_gutters} '
                          f'xg={x_gutters} yb={y_bounds} xb={x_bounds} '
                          f'groups={len(y_groups)}x{len(x_groups)}',
                          flush=True)
                y_edges = [0.0] + y_bounds + [1.0]
                x_edges = [0.0] + x_bounds + [1.0]
                if len(y_edges) <= 2 and len(x_edges) <= 2:
                    entry = dict(text_page)
                    entry['pdfPage'] = i
                    entry.pop('rect', None)
                    new_pages.append(entry)
                    continue

                # Build the row's panels. A row's caption columns may
                # sit under ONE full-width illustration (a single story
                # page typeset with two text columns) or under separate
                # per-column illustrations (one story page per column).
                # Decide per row: if the illustration band has a white
                # vertical gutter running through ALL of it, the columns
                # are separate pages; otherwise the row is one page.
                panel_infos = []
                for r in range(len(y_edges) - 1):
                    ylo, yhi = y_edges[r], y_edges[r + 1]
                    row_lines = [e for e in ocr_lines
                                 if ylo <= e[1] + e[3] / 2 < yhi]
                    # Bottom-most text cluster of the row = the captions;
                    # everything above it is the illustration band.
                    row_top_sorted = sorted(row_lines, key=lambda e: e[1])
                    illu_bot = yhi
                    if row_top_sorted:
                        cl = [row_top_sorted[-1]]
                        for e in reversed(row_top_sorted[:-1]):
                            if cl[0][1] - (e[1] + e[3]) <= 0.1:
                                cl.insert(0, e)
                            else:
                                break
                        illu_bot = min(e[1] for e in cl)
                    col_ranges = None
                    if len(x_edges) > 2 and illu_bot - ylo > 0.08:
                        igut = band_col_gutters(img_hi, ylo, illu_bot)
                        # Page-number badges printed in the illustrations
                        # (one per original story page, at its top left):
                        # a badge inside the RIGHT column proves the
                        # columns are separate pages even when the
                        # illustrations touch with no white gutter.
                        badges = [e for e in row_lines
                                  if e[1] < illu_bot
                                  and len(e[4].strip()) <= 3
                                  and re.fullmatch(r'\d{1,2}',
                                                   re.sub(r'\D', '',
                                                          e[4].strip())
                                                  or 'x')]
                        right_badge = any(e[0] + e[2] / 2 >= 0.35
                                          for e in badges)
                        if os.environ.get('DBGG2'):
                            print(f'DBGG2r {book_id} pdf{i} row{r}: '
                                  f'illu=({ylo},{illu_bot}) igut={igut} '
                                  f'badges={[(e[4], round(e[0], 2))
                                             for e in badges]}',
                                  flush=True)
                        # An illustration gutter is only trusted when it
                        # agrees with the caption-column boundary.
                        igut_ok = [g for g in igut
                                   if any(abs(g - xb2) <= 0.06
                                          for xb2 in x_bounds)]
                        if os.environ.get('DBGG2'):
                            print(f'DBGG2r {book_id} pdf{i} row{r}: '
                                  f'illu=({ylo},{illu_bot}) igut={igut} '
                                  f'ok={igut_ok} '
                                  f'badges={[(e[4], round(e[0], 2))
                                             for e in badges]}',
                                  flush=True)
                        if igut_ok or right_badge:
                            ced = [0.0] + igut_ok + [1.0] if igut_ok \
                                else list(x_edges)
                            col_ranges = [(ced[j], ced[j + 1])
                                          for j in range(len(ced) - 1)]
                    if col_ranges is None:
                        # Candidate full-width page. But if one side of
                        # the caption boundary has almost no ink in the
                        # illustration band (a title page or an empty
                        # half), the columns are separate pages.
                        col_ranges = [(x_edges[j], x_edges[j + 1])
                                      for j in range(len(x_edges) - 1)]
                        if len(x_edges) > 2 and illu_bot - ylo > 0.08:
                            xb0 = x_bounds[0]
                            left_lines = [e for e in row_lines
                                          if e[0] + e[2] / 2 < xb0]
                            right_lines = [e for e in row_lines
                                           if e[0] + e[2] / 2 >= xb0]

                            def cap_top(lines):
                                if not lines:
                                    return None
                                ls = sorted(lines, key=lambda e: e[1])
                                cl = [ls[-1]]
                                for e in reversed(ls[:-1]):
                                    if cl[0][1] - (e[1] + e[3]) <= 0.1:
                                        cl.insert(0, e)
                                    else:
                                        break
                                return min(e[1] for e in cl)

                            tl, tr = cap_top(left_lines), cap_top(right_lines)
                            # Two columns belong to ONE full-width page
                            # when their caption blocks start at the same
                            # height (one paragraph flowed into columns);
                            # a title page's text sits much higher than
                            # the story caption beside it.
                            aligned = (tl is not None and tr is not None
                                       and abs(tl - tr) <= 0.06)
                            ink_l = band_ink(img_hi, ylo, illu_bot,
                                             0.03, max(0.04, xb0 - 0.03))
                            ink_r = band_ink(img_hi, ylo, illu_bot,
                                             min(0.96, xb0 + 0.03), 0.97)
                            if aligned and min(ink_l, ink_r) >= 0.10:
                                col_ranges = [(0.0, 1.0)]
                            if os.environ.get('DBGG2'):
                                print(f'DBGG2m {book_id} pdf{i} row{r}: '
                                      f'tl={tl} tr={tr} ink={ink_l:.2f}/'
                                      f'{ink_r:.2f} merged={aligned and min(ink_l, ink_r) >= 0.10}',
                                      flush=True)
                    for clo, chi in col_ranges:
                        lines = [e for e in row_lines
                                 if clo <= e[0] + e[2] / 2 < chi]
                        text = ' '.join(
                            e[4] for e in
                            sorted(lines, key=lambda e: (e[1], e[0])))
                        panel_infos.append(([clo, ylo, chi, yhi], text))

                # Sentence assignment: text-cursor over the cell texts.
                page_buckets, s_scores = abt.assign_by_text(
                    sents_i, {j: info[1] for j, info in enumerate(panel_infos)},
                    with_scores=True)
                # Trailing narration that does not match the LAST panel's
                # caption (e.g. "At last, Biff and Chip went into a
                # hall.") describes the NEXT page's illustration: hand it
                # over to the following PDF page instead of pinning it to
                # a picture it does not belong to.
                if i != order_pdf[-1] and panel_infos:
                    last_key = len(panel_infos) - 1
                    moved = []
                    for idx in range(len(sents_i) - 1, -1, -1):
                        sc = s_scores[idx] if idx < len(s_scores) else None
                        if (sc is None or sc['key'] != last_key
                                or sc['confident']):
                            break
                        moved.append(sents_i[idx])
                    if 0 < len(moved) <= 3 and len(moved) < len(
                            page_buckets.get(last_key, [])):
                        page_buckets[last_key] = page_buckets[last_key][
                            :-len(moved)]
                        carry = list(reversed(moved))
                for j, (rect, _) in enumerate(panel_infos):
                    part = page_buckets.get(j, [])
                    entry = {'sentences': part, 'pdfPage': i,
                             'rect': [round(v, 4) for v in rect]}
                    if part:
                        entry['startMs'] = max(0, min(s['startMs']
                                                      for s in part) - 150)
                        entry['endMs'] = max(s['endMs'] for s in part) + 350
                    else:
                        prev_end = new_pages[-1].get('endMs', 0) if new_pages else 0
                        entry['startMs'] = prev_end
                        entry['endMs'] = prev_end
                    new_pages.append(entry)
            data['pages'] = new_pages
            json.dump(data, open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
            page_counts[book_id] = len(new_pages)
            print(f'{book_id}: {len(new_pages)} pages '
                  f'(lesson={lesson_edition})', flush=True)
    for level in lib['levels']:
        for b in level['books']:
            if b['id'] in page_counts:
                b['pages'] = page_counts[b['id']]
    json.dump(lib, open(lib_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, sort_keys=True)
    print('library page counts updated')


def crop_blue_frame_py(img):
    px = img.load()
    w, h = img.size

    def blue(x, y):
        r, g, b = px[x, y]
        return b > 130 and b > r * 1.6 and b > g * 1.4 and r < 130 and g < 130
    if not (blue(2, 2) and blue(w - 3, 2) and blue(2, h - 3) and blue(w - 3, h - 3)):
        return img
    step = max(1, min(w, h) // 120)
    left, top, right, bottom = w, h, -1, -1
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if not (b > 100 and b > r * 1.3 and b > g * 1.15
                    and r < 140 and g < 140):
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y
    if right <= left or bottom <= top:
        return img
    pad = max(4, min(w, h) // 90)
    return img.crop((max(0, left - pad), max(0, top - pad),
                     min(w - 1, right + pad) + 1,
                     min(h - 1, bottom + pad) + 1))


if __name__ == '__main__':
    main()
