import io
import math

from . import geometry, vision

from solver_frame3dd import run_frame3dd_analysis
from verify_checkpoints import verify_geometry_equilibrium, verify_material_detailing


def _heal(geojson, tol=0.05):
    """Sanitize AI geometry before solving.

    Snaps near-duplicate beam endpoints to a shared node set, drops degenerate
    (zero-length) beams, and marks every node pinned. This removes the floating /
    disconnected nodes that create mechanisms and singular stiffness matrices.
    """
    beams = []
    seen = set()
    rooms = []

    for feat in geojson.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") == "Polygon" and props.get("type") == "room":
            rooms.append(feat)
            continue
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        snapped = []
        for p in coords[:2]:
            p = tuple(p)
            match = next((q for q in seen if math.hypot(p[0] - q[0], p[1] - q[1]) < tol), None)
            if match is None:
                match = p
                seen.add(match)
            snapped.append(match)

        if math.hypot(snapped[0][0] - snapped[1][0], snapped[0][1] - snapped[1][1]) < tol:
            continue

        props = dict(feat.get("properties", {}))
        beams.append((snapped, props))

    new_features = []
    for i, coord in enumerate(sorted(seen)):
        new_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": list(coord)},
            "properties": {"type": "node", "support": "pinned", "node_id": i + 1},
        })

    for coords, props in beams:
        props.setdefault("type", "beam")
        new_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(c) for c in coords]},
            "properties": props,
        })

    # Add back the room polygons
    new_features.extend(rooms)

    return {"type": "FeatureCollection", "features": new_features}


def _run_loop(current, max_iterations):
    log = []

    for i in range(max_iterations):
        solver_res = run_frame3dd_analysis(current)
        check1 = verify_geometry_equilibrium(current, solver_res)
        check3 = verify_material_detailing(solver_res)

        if check1["passed"] and check3["passed"]:
            log.append(f"Iteration {i + 1}: all checkpoints passed.")
            return current, log, True, solver_res

        log.append(
            f"Iteration {i + 1}: equilibrium {'passed' if check1['passed'] else 'failed'}, "
            f"detailing {'passed' if check3['passed'] else 'failed'}."
        )
        current = _heal(current)

    solver_res = run_frame3dd_analysis(current)
    return current, log, False, solver_res


def run(values, image_bytes=None, image_mime=None, num_floors=1, max_iterations=3, raw_text=None, rooms=None):
    if rooms is None and image_bytes:
        layout = vision.extract(values, io.BytesIO(image_bytes))
        rooms = layout.get("rooms", [])

    current = _heal(geometry.build(values, rooms or [], num_floors, raw_text))
    return _run_loop(current, max_iterations)


def run_from_geojson(geojson, max_iterations=3):
    current = _heal(geojson)
    return _run_loop(current, max_iterations)
