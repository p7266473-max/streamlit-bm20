"""Deterministic DXF -> clean, AI-readable text summary.

Raw DXF files are hard for an LLM to digest (group-code tag soup). This
module converts an uploaded DXF into a precise, human-readable listing of
walls, pillars and rooms that an LLM can reason over to build the structural
grid GeoJSON.

This step is pure Python -- no AI -- so the numbers handed to the model are
exactly what the drawing contains. Unit handling is explicit so the AI never
has to guess the scale.
"""
import math
import os
import re
import tempfile

import ezdxf

from . import dxf as _dxf

# ---- Unit / scale handling -------------------------------------------------
# The demo plan is drawn in centimetres (1 drawing unit = 0.01 m). We detect
# the drawing unit so the AI always receives metres.
_MM_PER_UNIT = 0.001
_CM_PER_UNIT = 0.01
_M_PER_UNIT = 1.0

# Layers that are NOT structural walls for the summary (pillars are reported
# separately, the rest are annotation / furniture / dimension clutter).
_WALL_SKIP = {s.upper() for s in (
    set(_dxf._IGNORE_LAYERS) | {
        "PILLARS", "PILLAR", "FURNITURE", "FURNITURES", "ARROWS", "TEXT BORDERS",
        "TEXTBORDERS", "TEXT_BORDERS",
    }
)}


def _is_wall_layer(layer):
    return layer.upper() not in _WALL_SKIP


def _detect_scale(segments):
    coords = [c for seg in segments for c in seg]
    if not coords:
        return _CM_PER_UNIT
    max_extent = max(max(abs(x), abs(y)) for x, y in coords)
    if max_extent > 5000:
        return _MM_PER_UNIT
    if max_extent > 120:
        return _CM_PER_UNIT
    return _M_PER_UNIT


def _fmt(x, y):
    return f"{x:8.2f}, {y:8.2f}"


def _ft_in_to_m(text):
    """Parse a pair like "7'8'' x 13'1''" (feet/inches) into (m1, m2)."""
    parts = [p.strip() for p in re.split(r"[xX]|\u00d7", text) if p.strip()]
    out = []
    for p in parts:
        ft = re.search(r"(\d+)\s*['\u2032]", p)
        inch = re.search(r"(\d+)\s*(?:''|\u2033)", p)
        f = float(ft.group(1)) if ft else 0.0
        i = float(inch.group(1)) if inch else 0.0
        out.append(round(f * 0.3048 + i * 0.0254, 2))
    return out


# ---- Room names -------------------------------------------------------------
_ROOM_NAMES = {
    "KITCHEN", "BEDROOM", "BATHROOM", "HALL", "HALLWAY", "LOBBY", "LIVING",
    "LIVING ROOM", "DINING", "DINING ROOM", "SUNROOM", "UTILITY", "LAUNDRY",
    "STORE", "STORAGE", "OFFICE", "STUDY", "PANTRY", "WARDROBE", "CLOSET",
    "FOYER", "GARAGE", "PORCH", "BALCONY", "TOILET", "MASTER BEDROOM",
    "MASTER BATH", "DRAWING", "HALL2", "MAID",
}


def _decompose_texts(msp):
    texts = []
    for e in msp.query("TEXT"):
        t = e.dxf.text.strip()
        if t:
            texts.append((e.dxf.insert.x, e.dxf.insert.y, t))
    return texts


def _classify_rooms(texts, radius=120.0):
    dims = [(x, y, t) for x, y, t in texts if _dxf._DIMS_RE.search(t)]
    named = [(x, y, t) for x, y, t in texts
             if not _dxf._DIMS_RE.search(t)
             and any(w in t.upper() for w in _ROOM_NAMES)]
    rooms = []
    for i, (x, y, dim) in enumerate(dims):
        name = None
        for nx, ny, nt in named:
            if math.hypot(nx - x, ny - y) < radius:
                name = nt
                break
        rooms.append((x, y, name or f"Room {i + 1}", dim))
    return rooms


# ---- Main summary -----------------------------------------------------------
def summarize(dxf_bytes, name="uploaded.dxf"):
    """Return a clean text block describing the plan for an LLM."""
    if isinstance(dxf_bytes, (bytes, bytearray)):
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
            tmp_path = tmp.name
        try:
            doc = ezdxf.readfile(tmp_path)
        finally:
            os.remove(tmp_path)
    else:
        doc = ezdxf.read(dxf_bytes)
    msp = doc.modelspace()

    # Collect wall segments from non-annotation layers (same spirit as the
    # deterministic GeoJSON path, so the two never disagree).
    wall_rings = []   # list of (layer, [(x,y), ...], closed)
    wall_lines = []   # list of (layer, (x1,y1), (x2,y2)) loose lines
    for e in msp.query("LWPOLYLINE"):
        if not _is_wall_layer(e.dxf.layer):
            continue
        pts = list(e.get_points("xy"))
        if len(pts) >= 2:
            wall_rings.append((e.dxf.layer, pts, bool(e.closed)))
    for e in msp.query("LINE"):
        if not _is_wall_layer(e.dxf.layer):
            continue
        wall_lines.append((e.dxf.layer,
                           (e.dxf.start.x, e.dxf.start.y),
                           (e.dxf.end.x, e.dxf.end.y)))
    for e in msp.query("POLYLINE"):
        if not _is_wall_layer(e.dxf.layer):
            continue
        pts = [(p.x, p.y) for p in e.points()]
        if len(pts) >= 2:
            wall_rings.append((e.dxf.layer, pts, bool(e.is_closed)))

    # Pillars (dedicated structural layer, kept verbatim).
    pillars = []
    for e in msp.query("LWPOLYLINE"):
        if e.dxf.layer.upper() not in ("PILLARS", "PILLAR"):
            continue
        pts = list(e.get_points("xy"))
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pillars.append((e.dxf.layer, (min(xs), min(ys), max(xs), max(ys))))

    # Loose segments from every wall entity (edges of closed rings + lines).
    segments = []
    for layer, pts, closed in wall_rings:
        ring = list(pts) + ([pts[0]] if closed else [])
        for a, b in zip(ring, ring[1:]):
            segments.append((tuple(a), tuple(b)))
    for layer, a, b in wall_lines:
        segments.append((a, b))

    scale = _detect_scale(segments)
    unit_name = {_MM_PER_UNIT: "millimetres", _CM_PER_UNIT: "centimetres",
                 _M_PER_UNIT: "metres"}[scale]

    if not segments:
        raise ValueError(
            "No wall geometry found in the DXF modelspace. The file may only "
            "contain text or block references."
        )

    xs = [c[0] for s in segments for c in s]
    ys = [c[1] for s in segments for c in s]
    x0, x1 = min(xs) * scale, max(xs) * scale
    y0, y1 = min(ys) * scale, max(ys) * scale

    rooms = _classify_rooms(_decompose_texts(msp))

    lines = []
    lines.append("=" * 78)
    lines.append("ARCHITECTURAL FLOOR PLAN - CLEAN TEXT SUMMARY (for structural grid generation)")
    lines.append("=" * 78)
    lines.append(f"Source file : {name}")
    lines.append(f"Drawing unit: 1 unit = {scale} m ({unit_name})")
    lines.append(f"Plan extent : X {x0:.2f} m .. {x1:.2f} m  (width {x1 - x0:.2f} m)")
    lines.append(f"              Y {y0:.2f} m .. {y1:.2f} m  (depth {y1 - y0:.2f} m)")
    lines.append("")
    lines.append("All coordinates below are in METRES (already scaled from drawing units).")

    # ---- Walls ----
    lines.append("")
    lines.append(f"WALLS ({len(wall_rings) + len(wall_lines)} entities, "
                 f"{len(segments)} edges)")
    idx = 0
    for layer, pts, closed in wall_rings:
        w = max(p[0] for p in pts) - min(p[0] for p in pts)
        d = max(p[1] for p in pts) - min(p[1] for p in pts)
        lines.append(f"  Wall outline on layer '{layer}': {len(pts)} vertices, "
                     f"approx {w * scale:.2f} m x {d * scale:.2f} m")
        ring = list(pts) + ([pts[0]] if closed else [])
        for a, b in zip(ring, ring[1:]):
            idx += 1
            lines.append(f"    Entity {idx:3d}: Wall from ({_fmt(a[0] * scale, a[1] * scale)}) "
                         f"to ({_fmt(b[0] * scale, b[1] * scale)}) m")
    for layer, a, b in wall_lines:
        idx += 1
        lines.append(f"  Wall line on layer '{layer}':")
        lines.append(f"    Entity {idx:3d}: Wall from ({_fmt(a[0] * scale, a[1] * scale)}) "
                     f"to ({_fmt(b[0] * scale, b[1] * scale)}) m")

    # ---- Pillars ----
    lines.append("")
    if pillars:
        lines.append(f"STRUCTURAL PILLARS ({len(pillars)}) - each is ONE column at its centre:")
        for i, (layer, (x0p, y0p, x1p, y1p)) in enumerate(pillars, 1):
            cx, cy = (x0p + x1p) / 2 * scale, (y0p + y1p) / 2 * scale
            lines.append(f"  Pillar {i} on layer '{layer}': centre ({_fmt(cx, cy)}) m, "
                         f"size {(x1p - x0p) * scale:.2f} m x {(y1p - y0p) * scale:.2f} m")
    else:
        lines.append("STRUCTURAL PILLARS: none (all walls are regular load-bearing walls).")

    # ---- Rooms ----
    lines.append("")
    if rooms:
        lines.append(f"ROOMS ({len(rooms)}) - from dimension annotations:")
        for x, y, name, dim in rooms:
            m = _ft_in_to_m(dim)
            if len(m) == 2:
                lines.append(f"  Detected Room: approx {m[0]} m x {m[1]} m "
                             f"({name})  [printed: {dim}, near ({_fmt(x * scale, y * scale)}) m]")
            else:
                lines.append(f"  Detected Room: {dim} ({name}) near ({_fmt(x * scale, y * scale)}) m")
    else:
        lines.append("ROOMS: none detected from annotations.")

    lines.append("")
    lines.append("END OF PLAN SUMMARY.")
    return "\n".join(lines)
