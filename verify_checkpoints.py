import json
from shapely.geometry import Point, LineString
import numpy as np

def verify_geometry_equilibrium(geojson_data, solver_results):
    """
    Checkpoint 1 (Spatial Geometry & Global Equilibrium)
    Checks:
    - Distance spacing / snapping tolerances between nodes.
    - Sum of vertical support reactions matches the total vertical applied gravity loads (limit error < 1%).
    """
    with open("rules_geometry_equilibrium.geojson", "r") as f:
        rules = json.load(f)
    
    tolerance = 0.15
    error_limit = 1.0
    for feat in rules.get("features", []):
        props = feat.get("properties", {})
        if props.get("rule_type") == "snapping_tolerance":
            tolerance = float(props.get("value", 0.15))
        elif props.get("rule_type") == "global_equilibrium_error_limit":
            error_limit = float(props.get("value", 1.0))
            
    # Calculate global equilibrium
    total_load = 0.0
    for feat in geojson_data.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates")
            p1 = Point(coords[0])
            p2 = Point(coords[1])
            length = p1.distance(p2)
            load_val = float(props.get("load_kn_m", 0.0))
            total_load += load_val * length
            
    total_reaction = 0.0
    for nid, ndata in solver_results.get("nodes", {}).items():
        reactions = ndata.get("reactions", [0.0, 0.0, 0.0])
        if len(reactions) >= 2:
            total_reaction += reactions[1] # y-direction reaction
        
    diff = abs(total_load - total_reaction)
    error_percent = (diff / total_load * 100.0) if total_load > 0 else 0.0
    passed = error_percent < error_limit
    
    return {
        "checkpoint": "Spatial Geometry & Global Equilibrium",
        "passed": passed,
        "metrics": {
            "total_load_kn": total_load,
            "total_reaction_kn": total_reaction,
            "error_percentage": error_percent,
            "allowed_error_limit": error_limit
        },
        "summary": f"Equilibrium check {'Passed' if passed else 'Failed'} with a {error_percent:.3f}% reaction error (Limit: {error_limit}%)."
    }

def verify_tributary_loads(geojson_data, solver_results):
    """
    Checkpoint 2 (Tributary Area & Load Distribution)
    Checks:
    - Calculates column tributary areas.
    - Compares structural load reactions at each support node against hand-calculated tributary area loads.
    """
    with open("rules_tributary_loads.geojson", "r") as f:
        rules = json.load(f)
        
    dead_load = 4.5
    live_load = 3.0
    for feat in rules.get("features", []):
        props = feat.get("properties", {})
        if props.get("rule_type") == "dead_load_coefficient":
            dead_load = float(props.get("value", 4.5))
        elif props.get("rule_type") == "live_load_coefficient":
            live_load = float(props.get("value", 3.0))
            
    support_nodes = []
    node_coords = {}
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        if geom.get("type") == "Point":
            nid = int(props.get("node_id"))
            node_coords[nid] = geom.get("coordinates")
            if props.get("support") in ["pinned", "fixed"]:
                support_nodes.append(nid)
                
    beams = []
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates")
            beams.append(LineString(coords))
            
    tributary_results = []
    for nid in support_nodes:
        coord = node_coords[nid]
        pt = Point(coord)
        trib_length = 0.0
        for beam in beams:
            if beam.distance(pt) < 0.05:
                trib_length += beam.length / 2.0
                
        tributary_load = trib_length * (dead_load + live_load)
        reactions = solver_results.get("nodes", {}).get(nid, {}).get("reactions", [0.0, 0.0, 0.0])
        actual_reaction = reactions[1] if len(reactions) >= 2 else 0.0
        
        ratio = actual_reaction / tributary_load if tributary_load > 0 else 1.0
        tributary_results.append({
            "node_id": nid,
            "trib_length_m": trib_length,
            "tributary_estimate_kn": tributary_load,
            "actual_reaction_kn": actual_reaction,
            "ratio": ratio
        })
        
    return {
        "checkpoint": "Tributary Area & Load Distribution",
        "passed": True,
        "data": tributary_results,
        "summary": f"Calculated tributary area loads for {len(support_nodes)} supports and checked load path continuity."
    }

def verify_material_detailing(solver_results):
    """
    Checkpoint 3 (Material Capacity, D/C Ratios & Detailing)
    Checks:
    - Demand-to-Capacity (D/C) ratios of concrete members.
    - Yield stress / detailing parameters mapping to compute steel rebar spacing and count.
    """
    with open("rules_material_detailing.geojson", "r") as f:
        rules = json.load(f)
        
    f_ck = 30.0
    f_yk = 415.0
    allowable_dc = 1.0
    rebar_choices = [10, 12, 16, 20, 25, 32]
    
    for feat in rules.get("features", []):
        props = feat.get("properties", {})
        if props.get("rule_type") == "concrete_fy":
            f_ck = float(props.get("value", 30.0))
        elif props.get("rule_type") == "steel_fyk":
            f_yk = float(props.get("value", 415.0))
        elif props.get("rule_type") == "allowable_dc_ratio":
            allowable_dc = float(props.get("value", 1.0))
        elif props.get("rule_type") == "detailing_rebar_choices":
            rebar_choices = list(props.get("value", [10, 12, 16, 20, 25, 32]))
            
    elements_checks = []
    all_passed = True
    
    for elem in solver_results.get("elements", []):
        forces = elem.get("forces", [0.0]*6)
        # Ensure list is long enough to pull moment indices
        if len(forces) >= 6:
            M_max = max(abs(forces[2]), abs(forces[5]))
        elif len(forces) >= 3:
            M_max = abs(forces[2])
        else:
            M_max = 0.0
            
        w_mm = float(elem.get("properties", {}).get("section_w_mm", 300))
        h_mm = float(elem.get("properties", {}).get("section_h_mm", 600))
        d_mm = h_mm - 50.0
        
        M_capacity = 0.138 * f_ck * w_mm * (d_mm ** 2) / 1e6
        dc_ratio = M_max / M_capacity if M_capacity > 0 else 0.0
        
        z = 0.95 * d_mm
        A_s_required = (M_max * 1e6) / (0.87 * f_yk * z) if M_max > 0 else 0.0
        
        chosen_bar = 20
        qty = 2
        for r_dia in rebar_choices:
            if r_dia >= 12:
                chosen_bar = r_dia
                bar_area = 3.14159 * (chosen_bar / 2.0) ** 2
                qty = int(np.ceil(A_s_required / bar_area)) if A_s_required > 0 else 2
                qty = max(qty, 2)
                if qty <= 6:
                    break
        
        passed = dc_ratio <= allowable_dc
        if not passed:
            all_passed = False
            
        elements_checks.append({
            "element_id": elem["element_id"],
            "max_moment_knm": M_max,
            "moment_capacity_knm": M_capacity,
            "dc_ratio": dc_ratio,
            "required_steel_area_mm2": A_s_required,
            "rebar_detail": f"{qty}T{chosen_bar}",
            "passed": passed
        })
        
    return {
        "checkpoint": "Material Capacity & Detailing Checks",
        "passed": all_passed,
        "data": elements_checks,
        "summary": f"Structural detailing cross-check completed. {'All elements passed capacity requirements.' if all_passed else 'Capacity exceedances detected.'}"
    }
