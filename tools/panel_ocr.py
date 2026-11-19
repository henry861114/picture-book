#!/usr/bin/env python3
"""OCR a rendered PDF page and cluster the text lines into story pages."""
import re
import os


def ocr_lines(img_path):
    """Return [(text, x, y, w, h)] for each OCR line (Vision framework)."""
    import Vision as V
    from Foundation import NSURL
    req = V.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
    handler = V.VNImageRequestHandler.alloc().initWithURL_options_(
        NSURL.fileURLWithPath_(img_path), None)
    handler.performRequests_error_([req], None)
    lines = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        box = obs.boundingBox()
        text = cand[0].string()
        if not text or not text.strip():
            continue
        lines.append((text, box.origin.x, box.origin.y,
                      box.size.width, box.size.height))
    return lines


def cluster_pages(lines, max_x=1.0, max_y=1.0, x_gap=0.02, y_gap=0.06, depth=8):
    """Cluster OCR lines into story pages by recursive largest-gap split.

    At each level the biggest gap along x (between a line's right edge and
    the next line's left edge) and along y (between a line's bottom and the
    next line's top) is measured; the larger one is used to split the page
    into two regions, which are processed recursively. This handles
    stacked spreads, side-by-side spreads and 2x2 grids.

    Returns a list of clusters; each cluster is a list of
    (x, y, w, h, text) tuples.
    """
    ls = [(x, max_y - y - hh, ww, hh, t) for t, x, y, ww, hh in lines]
    out = []

    def split(items, l, t, r, b, d, mid_chain=False):
        if len(items) < 2 or d > depth:
            out.append((items, l, t, r, b))
            return
        # Largest x gap (right edge of a line -> left edge of the next).
        items_x = sorted(items, key=lambda e: e[0])
        best_x, best_x_v = None, x_gap
        for i in range(1, len(items_x)):
            prev_right = items_x[i - 1][0] + items_x[i - 1][2]
            gap = items_x[i][0] - prev_right
            if gap > best_x_v:
                best_x_v = gap
                best_x = i
        # Largest y gap.
        items_y = sorted(items, key=lambda e: e[1])
        best_y, best_y_v = None, y_gap
        for i in range(1, len(items_y)):
            prev_bottom = items_y[i - 1][1] + items_y[i - 1][3]
            gap = items_y[i][1] - prev_bottom
            if gap > best_y_v:
                best_y_v = gap
                best_y = i
        if os.environ.get('DBGX'):
            bx = f'{best_x_v:.2f}@{best_x}' if best_x else 'None'
            by = f'{best_y_v:.2f}@{best_y}' if best_y else 'None'
            print(f'DBGX d{d} region x[{l:.2f}-{r:.2f}] y[{t:.2f}-{b:.2f}] n={len(items)} xgap={bx} ygap={by}')
        if best_x is None and best_y is None:
            # No whitespace channel: a Lesson-edition spread holds equal
            # width pages that touch. Fall back to a midpoint split for
            # wide regions.
            tl = min(e[0] for e in items)
            tr = max(e[0] + e[2] for e in items)
            tt = min(e[1] for e in items)
            tb_ = max(e[1] + e[3] for e in items)
            if (tr - tl) > (tb_ - tt) * 1.6 and not mid_chain:
                mid = (tl + tr) / 2
                left = [e for e in items if (e[0] + e[2] / 2) < mid]
                right = [e for e in items if (e[0] + e[2] / 2) >= mid]
                if left and right:
                    split(left, l, t, mid, b, d + 1, True)
                    split(right, mid, t, r, b, d + 1, True)
                    return
            out.append((items, l, t, r, b))
            return
        mid_x = None if best_x is None else (best_x / len(items))
        if best_y is None or (best_x is not None
                              and best_x_v >= best_y_v * 0.6):
            left = items_x[:best_x]
            right = items_x[best_x:]
            mid = (left[-1][0] + left[-1][2] + right[0][0]) / 2
            split(left, l, t, mid, b, d + 1)
            split(right, mid, t, r, b, d + 1)
        else:
            top = items_y[:best_y]
            bottom = items_y[best_y:]
            mid = (top[-1][1] + top[-1][3] + bottom[0][1]) / 2
            split(top, l, t, r, mid, d + 1)
            split(bottom, l, mid, r, b, d + 1)

    split(ls, 0.0, 0.0, 1.0, 1.0, 0)
    if os.environ.get('DBGX'):
        print('DBGX final clusters:', len(out))
    return [c for c, l, t, r, b in out]
def page_bounds(cluster):
    l = min(e[0] for e in cluster)
    t = min(e[1] for e in cluster)
    r = max(e[0] + e[2] for e in cluster)
    b = max(e[1] + e[3] for e in cluster)
    return l, t, r, b
