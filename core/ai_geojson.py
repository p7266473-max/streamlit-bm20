"""AI stage: clean plan text -> structural grid GeoJSON.

The DXF -> clean text step (core/dxf_text.py) produces a human-readable summary.
This module asks the LLM to identify STRUCTURAL COLUMN locations from that text
(columns at wall corners/L-T junctions, pillar centres, plus intermediate
columns so no span > 4.2 m). The model returns compact coordinate pairs; beams
are then built deterministically in Python (connect collinear adjacent columns).

Why split: the free-tier model truncates large GeoJSON output. Asking only for
coordinates keeps the reply small enough to complete. The reply is still
validated: coordinates must be finite numbers inside the plan; every beam
endpoint must match a column exactly.

If the LLM fails every stage, raise so callers can fall back to the
deterministic core/structural.py generator.
"""
import json
import math
import re

from . import transport

MAX_BEAM_M = 4.2


_SYSTEM = (
    "You are a structural engineer. Given this plan text, identify column "
    "locations: place a column at every wall corner, L-T junction, and each "
    "pillar centre. Add intermediate columns on long wall runs so no span "
    "between columns exceeds 4.2 m. Return ONLY semicolon-separated coordinate "
    "pairs (metres): x1,y1; x2,y2; x3,y3; ... end your list with END. No prose."
)


def _r2(v):
    return round(float(v), 2)


def _extract_pairs(raw):
    nums = re.findall(r"-?\d*(?:\.\d+)", raw)
    out = []
    i = 0
    vals = []
    for n in nums:
        try:
            vals.append(float(n))
        except ValueError:
            pass
    pairs = []
    for i in range(0, len(vals) - 1, 2):
        pairs.append((_r2(vals[i]), _r2(vals[i + 1])))
    return pairs


def _build_beams(columns):
    cols = sorted(set(columns))
    by_x = {}
    by_y = {}
    for i, (x, y) in enumerate(cols):
        by_x.setdefault(x, []).append((i, y))
        by_y.setdefault(y, []).append((i, x))

    def connect(groups):
        beams = []
        for coord, pts in groups.items():
            pts.sort(key=lambda t: t[1])
            for k in range(len(pts) - 1):
                a_idx, a_val = pts[k]
                b_idx, b_val = pts[k + 1]
                span = b_val - a_val
                if span <= MAX_BEAM_M + 0.02 and span > 0.05:
                    a = cols[a_idx]
                    b = cols[b_idx]
                    if a != b:
                        beams.append((a, b))
        return beams

    beams = connect(by_x) + connect(by_y)
    seen = set()
    members = []
    for a, b in beams:
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        members.append((a, b))
    return members


def _geojson(columns, beams):
    features = []
    for i, c in enumerate(sorted(columns), 1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c[0], c[1]]},
            "properties": {"type": "node", "node_id": i, "support": "pinned"},
        })
    for i, (a, b) in enumerate(beams, 1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(a), list(b)]},
            "properties": {
                "type": "beam", "beam_id": i,
                "load_kn_m": 20.0, "section_w_mm": 300, "section_h_mm": 600,
            },
        })
    return {"type": "FeatureCollection", "features": features}


_CLUSTER_TOL_M = 0.5

def _cluster(pts, tol=_CLUSTER_TOL_M):
    merged = []
    for p in sorted(pts):
        placed = False
        for mg in merged:
            if math.dist(p, mg[0]) < tol:
                mg.append(p)
                placed = True
                break
        if not placed:
            merged.append([p])
    out = []
    for g in merged:
        cx = sum(p[0] for p in g) / len(g)
        cy = sum(p[1] for p in g) / len(g)
        out.append((_r2(cx), _r2(cy)))
    return out

def _validate_columns(pairs, bbox):
    xmin, ymin, xmax, ymax = bbox
    kept = []
    for x, y in pairs:
        if math.isfinite(x) and math.isfinite(y):
            if xmin - 0.3 <= x <= xmax + 0.3 and ymin - 0.3 <= y <= ymax + 0.3:
                kept.append((x, y))
    return _cluster(kept)


def from_text(values, text_summary, model_key="K4", max_tokens=2000):
    user_text = text_summary

    m = re.search(r"X\[([0-9.]+),\s*([0-9.]+)\]\s*[x×X]\s*Y\[([0-9.]+),\s*([0-9.]+)\]", text_summary)
    if m:
        bbox = (float(m.group(1)), float(m.group(3)),
                float(m.group(2)), float(m.group(4)))
    else:
        bbox = (0.0, 0.0, 20.0, 20.0)

    pairs = []
    for _ in range(3):
        model = transport.model(values, model_key, max_tokens)
        resp = model([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_text},
        ])
        raw = str(getattr(resp, "content", "") or "").strip()
        if raw and raw != "None":
            pairs = _extract_pairs(raw)
            if len(pairs) >= 5:
                break

    pairs = _validate_columns(pairs, bbox)
    if not pairs:
        raise RuntimeError("AI failed to extract column coordinates.")

    columns = set(pairs)
    beams = _build_beams(columns)
    if not beams:
        raise RuntimeError("No valid beam connections found from AI columns.")

    return _geojson(columns, beams)
