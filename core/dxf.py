import math
import os
import re
import tempfile

import ezdxf

_IGNORE_LAYERS = {
    "FOUNDATIONS", "GRID_LINES", "GRID", "AXIS", "DIMENSION", "DIMENSIONS",
    "TEXT", "TEXTS", "TEXT BORDERS", "ANNOTATION", "ARROWS",
    "FURNITURE", "FURNITURES", "DOOR", "DOORS", "WINDOW", "WINDOWS",
    "HATCH", "HATCHING", "STAIRS", "ELEVATION",
}


def _snap(points, tol):
    snapped = []
    for p in points:
        match = next((q for q in snapped if math.hypot(p[0] - q[0], p[1] - q[1]) < tol), None)
        if match is None:
            match = tuple(p)
            snapped.append(match)
    return snapped


def _find(nodes, pt, tol):
    for i, n in enumerate(nodes):
        if math.hypot(pt[0] - n[0], pt[1] - n[1]) < tol:
            return i
    return None


def _build_geojson(segments, tol):
    nodes = _snap([c for seg in segments for c in seg], tol)

    incidences = [0] * len(nodes)
    kept = []
    for a, b in segments:
        ia, ib = _find(nodes, a, tol), _find(nodes, b, tol)
        if ia is None or ib is None or ia == ib:
            continue
        incidences[ia] += 1
        incidences[ib] += 1
        kept.append((ia, ib))

    col_map = {}
    for i in range(len(nodes)):
        if incidences[i] >= 2:
            col_map[i] = len(col_map)
    columns = [nodes[i] for i in col_map]
    if not columns:
        raise ValueError(
            f"No junction nodes (columns) detected in the DXF: {len(segments)} line segments "
            f"were found but none of their endpoints meet at a shared junction "
            f"(snap tolerance {tol:.4f} m). Check that beams are drawn as connected lines."
        )

    features = []
    for i, c in enumerate(columns, 1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c[0], c[1]]},
            "properties": {"type": "node", "node_id": i, "support": "pinned"},
        })

    beam_id = 1
    for ia, ib in kept:
        if ia not in col_map or ib not in col_map:
            continue
        a, b = columns[col_map[ia]], columns[col_map[ib]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[a[0], a[1]], [b[0], b[1]]]},
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


def extract(dxf_bytes, tol=0.05):
    """Deterministic DXF -> structural GeoJSON conversion (no AI).

    Reads LINE / LWPOLYLINE geometry from the modelspace, snaps duplicate
    endpoints into a shared node set, keeps only junction nodes (where 2+
    beam segments meet) as pinned columns, and re-emits each segment as a beam.
    Units are assumed meters; drawings whose extents exceed 100 are scaled
    down by 1000 (mm -> m).
    """
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

    segments = []
    for e in msp.query("LINE"):
        if e.dxf.layer in _IGNORE_LAYERS:
            continue
        segments.append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
    for e in msp.query("LWPOLYLINE"):
        if e.dxf.layer in _IGNORE_LAYERS:
            continue
        pts = list(e.get_points("xy"))
        if len(pts) < 2:
            continue
        ring = list(pts) + ([pts[0]] if e.closed else [])
        for a, b in zip(ring, ring[1:]):
            segments.append((tuple(a), tuple(b)))
    for e in msp.query("POLYLINE"):
        if e.dxf.layer in _IGNORE_LAYERS:
            continue
        pts = list(e.points())
        if len(pts) < 2:
            continue
        ring = list(pts) + ([pts[0]] if e.is_closed else [])
        for a, b in zip(ring, ring[1:]):
            segments.append(((a.x, a.y), (b.x, b.y)))

    if not segments:
        # No line geometry at all: maybe pure annotation. Try rooms anyway.
        rooms = _extract_rooms(msp)
        if rooms:
            return {"type": "architectural_plan", "rooms": rooms}
        raise ValueError(
            "No LINE / POLYLINE geometry found in the DXF modelspace. "
            "The file may only contain text, blocks, or unsupported entities."
        )

    # Architectural 2D plans carry room dimension annotations (e.g. "14'2'' x 12'4''").
    # For these, place columns structurally: collapse double-line walls to
    # centrelines and put columns at junctions/corners plus intermediate columns
    # on long spans (thumb rules). Fall back to the rooms path only if the
    # deterministic grid cannot be derived.
    rooms = _extract_rooms(msp)
    if rooms:
        from . import structural
        wall_entities = list(msp.query("LWPOLYLINE[layer=='Walls']"))
        pillar_entities = list(msp.query("LWPOLYLINE[layer=='Pillars']"))
        try:
            return structural.plan_to_grid(wall_entities, pillar_entities)
        except ValueError:
            return {"type": "architectural_plan", "rooms": rooms}

    all_coords = [c for seg in segments for c in seg]
    max_extent = max(max(abs(x), abs(y)) for x, y in all_coords)
    if max_extent > 10000:
        segments = [((x1 / 1000.0, y1 / 1000.0), (x2 / 1000.0, y2 / 1000.0)) for (x1, y1), (x2, y2) in segments]
        max_extent /= 1000.0

    # Adaptive snap tolerance: scale with drawing size so slightly-offline
    # endpoints still join into junctions.
    base_tol = max(tol, 0.002 * max_extent)

    last_err = None
    for tol_i in (base_tol, base_tol * 4, base_tol * 16):
        try:
            return _build_geojson(segments, tol_i)
        except ValueError as e:
            last_err = e
    raise last_err


_DIMS_RE = re.compile(r"\d\s*['\u2032]|['\u2032]['\u2032]\s*[xX]\s*\d")


def _extract_rooms(msp, name_radius=200.0):
    """Deterministic room extraction from architectural DXF TEXT annotations.

    Dimension texts like "14'2'' x 12'4''" are paired with the nearest room
    name text to produce [{name, dims}] used to regenerate the layout.
    """
    texts = []
    for e in msp.query("TEXT"):
        t = e.dxf.text.strip()
        if not t:
            continue
        texts.append((e.dxf.insert.x, e.dxf.insert.y, t))

    dims = [(x, y, t) for x, y, t in texts if _DIMS_RE.search(t)]
    names = [(x, y, t) for x, y, t in texts if not _DIMS_RE.search(t)]

    rooms = []
    for i, (dx, dy, dim) in enumerate(dims):
        name = None
        for nx, ny, nt in names:
            if math.hypot(nx - dx, ny - dy) < name_radius:
                name = nt
                break
        rooms.append({"name": name or f"Room {i + 1}", "dims": dim})

    return rooms
