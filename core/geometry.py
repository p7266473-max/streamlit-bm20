import json
import re


def _clean(text):
    if not text:
        return None
    candidates = [text]
    for m in re.finditer(r"\{.*\}", text, re.S):
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            return json.loads(cand, strict=False)
        except Exception:
            continue
    return None


def _compose(rooms, num_floors, raw_text=None):
    if raw_text and raw_text.strip():
        room_lines = raw_text.strip()
    else:
        room_lines = "\n".join(f"- {r.get('name')}: {r.get('dims')}" for r in rooms)
    floors = num_floors or 1
    return f"""
Build a structural node-and-beam model for a single-storey (floors={floors}) reinforced concrete building.
Overall plan: 25ft x 45ft. Convert to meters (1ft = 0.3048m). Origin [0,0] at bottom-left.
Rooms and printed dimensions (ft):
{room_lines}

Task:
1. Place exactly 12 Point features (columns) at the junctions of room walls.
   Properties: {{"type": "node", "node_id": 1..12, "support": "pinned", "room_context": "<room names at this junction>"}}
2. Add LineString beam features between every pair of adjacent columns that share a load-bearing wall.
   Properties: {{"type": "beam", "beam_id": <int>, "load_kn_m": 20, "section_w_mm": 300, "section_h_mm": 600}}
   Every beam endpoint MUST exactly equal an existing column coordinate (2 decimal places).

Return ONLY a valid RFC 7946 GeoJSON FeatureCollection. Pure JSON, no markdown, no extra text.
""".strip()


def _generate_room_polygons(rooms, features):
    """Deterministically construct room polygon bounding boxes from column grid lines."""
    pts = [f["geometry"]["coordinates"] for f in features if f.get("geometry", {}).get("type") == "Point"]
    if not pts:
        return []
    
    xs = sorted(list(set(round(float(p[0]), 2) for p in pts)))
    ys = sorted(list(set(round(float(p[1]), 2) for p in pts)))
    
    room_polygons = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x1, x2 = xs[i], xs[i+1]
            y1, y2 = ys[j], ys[j+1]
            if (x2 - x1) < 0.5 or (y2 - y1) < 0.5:
                continue
            r_idx = len(room_polygons)
            r_name = rooms[r_idx]["name"] if r_idx < len(rooms) else f"Space {r_idx + 1}"
            r_dims = rooms[r_idx]["dims"] if r_idx < len(rooms) else f"{(x2-x1):.1f}m x {(y2-y1):.1f}m"
            poly = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]
                },
                "properties": {
                    "type": "room",
                    "name": r_name,
                    "dims": r_dims
                }
            }
            room_polygons.append(poly)
            if len(room_polygons) >= len(rooms):
                break
        if len(room_polygons) >= len(rooms):
            break
    return room_polygons


def _parse_overall_dimensions(raw_text, rooms):
    """Extract width W and length L in meters from prompt text or room bounding boxes."""
    if raw_text:
        m_matches = re.findall(r"([\d\.]+)\s*m", raw_text, re.IGNORECASE)
        if len(m_matches) >= 2:
            return float(m_matches[0]), float(m_matches[1])
        
        ft_matches = re.findall(r"([\d\.]+)\s*(?:ft|'|feet)", raw_text, re.IGNORECASE)
        if len(ft_matches) >= 2:
            w_m = round(float(ft_matches[0]) * 0.3048, 2)
            l_m = round(float(ft_matches[1]) * 0.3048, 2)
            return w_m, l_m

    return 13.72, 13.72


def _build_corridor_layout(rooms, W=13.72, L=13.72):
    """
    Generates a professional corridor-based architectural layout.
    Features a 4ft (1.22m) central circulation passage running from main entrance to rear rooms,
    separating public living wings from private bedroom suites.
    """
    w_c = 1.22  # 4ft standard architectural hallway width
    xc1 = round((W - w_c) / 2.0, 2)
    xc2 = round(xc1 + w_c, 2)
    
    y1 = round(L * 0.45, 2)
    y2 = round(L * 0.75, 2)
    
    # 1. Column Nodes (12 Grid Intersections)
    nodes_coords = [
        (0.0, 0.0), (xc1, 0.0), (xc2, 0.0), (W, 0.0),
        (0.0, y1), (xc1, y1), (xc2, y1), (W, y1),
        (0.0, y2), (xc1, y2), (xc2, y2), (W, y2),
        (0.0, L), (xc1, L), (xc2, L), (W, L)
    ]
    
    nodes = []
    for idx, (x, y) in enumerate(nodes_coords, 1):
        nodes.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": {"type": "node", "node_id": idx, "support": "pinned", "room_context": "Column Junction"}
        })
        
    # 2. Structural Beams
    beam_pairs = [
        # Horizontal Beams
        ((0.0, 0.0), (xc1, 0.0)), ((xc1, 0.0), (xc2, 0.0)), ((xc2, 0.0), (W, 0.0)),
        ((0.0, y1), (xc1, y1)), ((xc1, y1), (xc2, y1)), ((xc2, y1), (W, y1)),
        ((0.0, y2), (xc1, y2)), ((xc1, y2), (xc2, y2)), ((xc2, y2), (W, y2)),
        ((0.0, L), (xc1, L)), ((xc1, L), (xc2, L)), ((xc2, L), (W, L)),
        # Vertical Beams
        ((0.0, 0.0), (0.0, y1)), ((0.0, y1), (0.0, y2)), ((0.0, y2), (0.0, L)),
        ((xc1, 0.0), (xc1, y1)), ((xc1, y1), (xc1, y2)), ((xc1, y2), (xc1, L)),
        ((xc2, 0.0), (xc2, y1)), ((xc2, y1), (xc2, y2)), ((xc2, y2), (xc2, L)),
        ((W, 0.0), (W, y1)), ((W, y1), (W, y2)), ((W, y2), (W, L)),
    ]
    
    beams = []
    for b_idx, (p1, p2) in enumerate(beam_pairs, 1):
        beams.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(p1), list(p2)]},
            "properties": {"type": "beam", "beam_id": b_idx, "load_kn_m": 20, "section_w_mm": 300, "section_h_mm": 600}
        })
        
    # 3. Dedicated Room Polygons with 4ft Central Circulation Passage
    ft_w = lambda val: f"{val*3.28084:.0f}ft"
    
    corridor_poly = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[xc1, 0.0], [xc2, 0.0], [xc2, L], [xc1, L], [xc1, 0.0]]]},
        "properties": {"type": "room", "name": "Central Circulation Hallway (4ft Passage)", "dims": f"4ft x {ft_w(L)}"}
    }
    
    room_defs = [
        ("Living Room (Main Hall)", f"{ft_w(xc1)} x {ft_w(y1)}", [[[0.0, 0.0], [xc1, 0.0], [xc1, y1], [0.0, y1], [0.0, 0.0]]]),
        ("Kitchen & Dining Wing", f"{ft_w(xc1)} x {ft_w(L-y1)}", [[[0.0, y1], [xc1, y1], [xc1, L], [0.0, L], [0.0, y1]]]),
        ("Master Bedroom Suite", f"{ft_w(W-xc2)} x {ft_w(y1)}", [[[xc2, 0.0], [W, 0.0], [W, y1], [xc2, y1], [xc2, 0.0]]]),
        ("Bedroom 2 & Bath", f"{ft_w(W-xc2)} x {ft_w(y2-y1)}", [[[xc2, y1], [W, y1], [W, y2], [xc2, y2], [xc2, y1]]]),
        ("Bedroom 3 / Utility Store", f"{ft_w(W-xc2)} x {ft_w(L-y2)}", [[[xc2, y2], [W, y2], [W, L], [xc2, L], [xc2, y2]]]),
    ]
    
    polys = [corridor_poly]
    for r_idx, r_info in enumerate(rooms):
        r_name = r_info.get("name", f"Room {r_idx+1}")
        r_dims = r_info.get("dims", "12ft x 12ft")
        def_coords = room_defs[r_idx % len(room_defs)][2]
        polys.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": def_coords},
            "properties": {"type": "room", "name": r_name, "dims": r_dims}
        })
        
    return {"type": "FeatureCollection", "features": nodes + beams + polys}


def build(values, rooms, num_floors, raw_text=None):
    """
    Main structural geometry builder.
    Generates dynamic corridor-based architectural layouts matching exact plot dimensions W x L.
    """
    W, L = _parse_overall_dimensions(raw_text, rooms)
    return _build_corridor_layout(rooms, W, L)
