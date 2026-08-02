"""Deterministic architectural-plan -> structural grid generation (no AI).

Implements standard column-placement thumb rules:
  1. Corner & junction rule: columns at every wall corner / L / T junction.
  2. Spacing rule: column centre-to-centre spacing ~3-4 m (10-13 ft);
     spans beyond the limit get intermediate columns so none exceed ~14 ft.
  3. Strict orthogonal grid: columns only where horizontal and vertical wall
     faces cross (or at real pillar positions), never random.
  4. Beams run along wall lines and always terminate at a column.
"""
import math

MAX_SPAN_M = 4.2          # max centre-to-centre span between columns (~14 ft)
SCALE_M_PER_UNIT = 0.01   # architectural plans drawn in centimetres
_ANGLE_TOL = 1.0          # tolerance for treating a segment as axis-aligned (units)
_COL_MERGE_M = 0.35       # merge junction columns closer than this


def _decompose(entities):
    hs, vs = [], []
    for e in entities:
        pts = list(e.get_points("xy"))
        ring = list(pts) + ([pts[0]] if e.closed else [])
        for a, b in zip(ring, ring[1:]):
            ax, ay, bx, by = a[0], a[1], b[0], b[1]
            if abs(ay - by) <= _ANGLE_TOL:
                y = ay
                x1, x2 = sorted((ax, bx))
                if x2 - x1 > 1e-6:
                    hs.append((y, x1, x2))
            elif abs(ax - bx) <= _ANGLE_TOL:
                x = ax
                y1, y2 = sorted((ay, by))
                if y2 - y1 > 1e-6:
                    vs.append((x, y1, y2))
    return hs, vs


def _cluster_cols(points, tol):
    cols = []
    for p in points:
        for c in cols:
            if math.hypot(p[0] - c[0], p[1] - c[1]) < tol:
                c[0] = (c[0] * c[2] + p[0]) / (c[2] + 1)
                c[1] = (c[1] * c[2] + p[1]) / (c[2] + 1)
                c[2] += 1
                break
        else:
            cols.append([p[0], p[1], 1])
    return cols


def _pillar_rects(pillar_entities, scale):
    rects = []
    centers = []
    for e in pillar_entities:
        pts = list(e.get_points("xy"))
        if not pts:
            continue
        xs = [p[0] * scale for p in pts]
        ys = [p[1] * scale for p in pts]
        rects.append((min(xs), min(ys), max(xs), max(ys)))
        centers.append(((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0))
    return rects, centers


def plan_to_grid(wall_entities, pillar_entities, scale=SCALE_M_PER_UNIT):
    hs, vs = _decompose(wall_entities + pillar_entities)
    pillar_rects, pillar_centers = _pillar_rects(pillar_entities, scale)

    # --- Wall CENTRELINE grid lines: the two faces of each double-line wall
    #     collapse to one clean orthogonal line (rule 3). ---
    def centrelines(coords, tol):
        out = []
        for c in sorted(coords):
            for g in out:
                if abs(c - g[0]) < tol:
                    g[1].append(c)
                    break
            else:
                out.append([c, [c]])
        return sorted(sum(s) / len(s) for _, s in out)

    ylines = centrelines({h[0] * scale for h in hs}, 0.45)
    xlines = centrelines({v[0] * scale for v in vs}, 0.45)

    # --- Wall runs (continuous wall coverage) keyed by centreline coord. ---
    def wall_runs(segments, coord_idx, scale):
        runs = {}
        for (c, c1, c2) in segments:
            c_m = c * scale
            c1, c2 = c1 * scale, c2 * scale
            key = round(min(xlines, key=lambda x: abs(x - c_m))
                        if coord_idx == 1 else
                        min(ylines, key=lambda y: abs(y - c_m)), 3)
            runs.setdefault(key, []).append((c1, c2))
        merged = {}
        for c, segs in runs.items():
            segs = sorted(segs)
            out = []
            cur = list(segs[0])
            for s in segs[1:]:
                if s[0] <= cur[1] + 0.05:
                    cur[1] = max(cur[1], s[1])
                else:
                    out.append(tuple(cur))
                    cur = list(s)
            out.append(tuple(cur))
            merged[c] = out
        return merged

    h_runs = wall_runs(hs, 0, scale)
    v_runs = wall_runs(vs, 1, scale)

    # --- Junction / corner columns: where a horizontal wall face crosses a
    #     vertical wall face. Double-line walls produce a tight cluster of
    #     crossings at each real junction, merged into one column. ---
    crossings = []
    for (y, x1, x2) in hs:
        for (x, y1, y2) in vs:
            if x1 <= x <= x2 and y1 <= y <= y2:
                crossings.append((x * scale, y * scale))

    cols = _cluster_cols(crossings, _COL_MERGE_M)

    # Snap junction columns onto the centreline grid so double-line wall faces
    # collapse to single clean orthogonal columns.
    snapped = {}
    for (cx, cy, _) in cols:
        nx = min(xlines, key=lambda x: abs(x - cx))
        ny = min(ylines, key=lambda y: abs(y - cy))
        snapped[(round(nx, 4), round(ny, 4))] = None
    cols = [[x, y, 1] for (x, y) in snapped]

    # A pillar rectangle is a single structural column, not its four corners.
    cols = [c for c in cols if not any(
        (r0 - 0.2 <= c[0] <= r2 + 0.2) and (r1 - 0.2 <= c[1] <= r3 + 0.2)
        for (r0, r1, r2, r3) in pillar_rects
    )]
    for (cx, cy) in pillar_centers:
        nx = min(xlines, key=lambda x: abs(x - cx))
        ny = min(ylines, key=lambda y: abs(y - cy))
        cols.append([round(nx, 4), round(ny, 4), 1])
    cols = _cluster_cols([(c[0], c[1]) for c in cols], 0.15)

    if len(cols) < 2:
        raise ValueError("Could not derive a structural column grid from the plan walls.")

    cols = [(round(c[0], 4), round(c[1], 4)) for c in cols]

    # --- Beams: consecutive columns along each wall run, only where a wall
    #     actually spans them. Endpoints are exact column coordinates. ---
    beams = []

    def covered(intervals, a, b):
        tot = 0.0
        for (c1, c2) in intervals:
            tot += max(0.0, min(c2, b) - max(c1, a))
        return tot >= (b - a) * 0.6

    def link_axis(runs, key, sort):
        lines = {}
        for (x, y) in cols:
            lines.setdefault(round(x if key == 0 else y, 3), []).append((x, y))
        for c, members in lines.items():
            intervals = runs.get(c, [])
            members = sorted(members, key=lambda p: p[sort])
            for a, b in zip(members, members[1:]):
                if covered(intervals, a[sort], b[sort]) and b[sort] - a[sort] > 0.3:
                    beams.append(((a[0], a[1]), (b[0], b[1])))

    link_axis(h_runs, key=1, sort=0)
    link_axis(v_runs, key=0, sort=1)

    # --- Spacing rule: intermediate columns on long wall spans. ---
    extra = set()
    for c, intervals in h_runs.items():
        on = [(x, y) for (x, y) in cols if abs(y - c) < 0.1]
        line_y = round(sum(y for _, y in on) / len(on), 4)
        xs = sorted(x for x, _ in on)
        for a, b in zip(xs, xs[1:]):
            if not covered(intervals, a, b):
                continue
            n = max(0, math.ceil((b - a) / MAX_SPAN_M) - 1)
            for k in range(1, n + 1):
                extra.add((round(a + (b - a) * k / (n + 1), 4), line_y))
    for c, intervals in v_runs.items():
        on = [(x, y) for (x, y) in cols if abs(x - c) < 0.1]
        line_x = round(sum(x for x, _ in on) / len(on), 4)
        ys = sorted(y for _, y in on)
        for a, b in zip(ys, ys[1:]):
            if not covered(intervals, a, b):
                continue
            n = max(0, math.ceil((b - a) / MAX_SPAN_M) - 1)
            for k in range(1, n + 1):
                extra.add((line_x, round(a + (b - a) * k / (n + 1), 4)))

    cols = sorted(set(cols) | extra)

    # Final merge pass: near-identical duplicate columns only (columns are
    # already snapped onto the centreline grid, so this only removes exact
    # overlaps from pillar centres / spacing inserts).
    cols = sorted((round(c[0], 4), round(c[1], 4)) for c in _cluster_cols(cols, 0.15))

    # --- Rebuild beams with intermediate columns included ---
    beams = []
    link_axis(h_runs, key=1, sort=0)
    link_axis(v_runs, key=0, sort=1)

    features = []
    for i, (x, y) in enumerate(cols, 1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": {"type": "node", "node_id": i, "support": "pinned"},
        })
    beam_id = 1
    for (ax, ay), (bx, by) in beams:
        if math.hypot(bx - ax, by - ay) < 1e-6:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[ax, ay], [bx, by]]},
            "properties": {
                "type": "beam",
                "beam_id": beam_id,
                "load_kn_m": 20.0,
                "section_w_mm": 300,
                "section_h_mm": 600,
            },
        })
        beam_id += 1

    return {"type": "FeatureCollection", "features": features}
