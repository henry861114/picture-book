#!/usr/bin/env python3
"""Assign narration sentences to OCR text panels.

Every sentence goes to the panel whose OCR text contains the best matching
window (sliding window of the sentence's own word length). This is robust
against illustration text and OCR noise inside the panels. A forward-only
pointer keeps the assignment monotonic in reading order; sentences with no
confident match stay on the current panel.
"""
import difflib
import re
import os


def words(text):
    return [w for w in re.sub(r"[^a-z0-9' ]", ' ', (text or '').lower()).split()
            if w]


def best_window_ratio(sw, pw):
    """Best similarity between the sentence and any window of the panel."""
    if not pw:
        return 0.0
    n = len(sw)
    if n == 0:
        return 0.0
    best = 0.0
    for start in range(0, max(1, len(pw) - n + 1)):
        window = pw[start:start + n]
        r = difflib.SequenceMatcher(None, sw, window).ratio()
        if r > best:
            best = r
            if best > 0.95:
                break
    return best


def assign_by_text(sentences, panel_texts, with_scores=False):
    """sentences: list of dicts with 'en'; panel_texts: {key: text}.

    Returns {key: [sentence dicts]} in narration order.  With
    with_scores, also returns [{idx, key, r, confident}] per input
    sentence (idx = position in the input list).
    """
    order = sorted(panel_texts)
    if not order:
        return ({}, []) if with_scores else {}
    pw = {k: words(t) for k, t in panel_texts.items()}
    usable = [k for k in order if pw[k]]
    if not usable:
        buckets = {k: list(sentences) for k in order}
        if with_scores:
            return buckets, []
        return buckets
    cur = 0
    buckets = {k: [] for k in order}
    scores = []
    for idx, s in enumerate(sentences):
        sw = words(s.get('en', ''))
        if not sw:
            continue
        best = None
        for j in range(cur, len(usable)):
            k = usable[j]
            r = best_window_ratio(sw, pw[k])
            if best is None or r > best[0]:
                best = (r, j, k)
        r, j, k = best
        if os.environ.get('DBGA'):
            kk = usable[cur] if r < 0.45 else k
            print(f'DBGA "{s.get("en","")[:36]}" -> [{j}]{k} '
                  f'text={pw[k][:30]!r} r={r:.2f}'
                  f'{" STAY->"+str(kk) if r < 0.45 else ""}', flush=True)
        if r < 0.45:
            k = usable[cur]          # stay on the current panel
        else:
            cur = j                  # advance the pointer
        buckets[k].append(s)
        scores.append({'idx': idx, 'key': k, 'r': r,
                       'confident': r >= 0.45})
    if with_scores:
        return buckets, scores
    return buckets
