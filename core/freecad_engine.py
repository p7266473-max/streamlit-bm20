import os
import json
import subprocess

def generate_freecad_model(geojson_data, output_fcstd="assets/building_model.FCStd", output_step="assets/building_model.step"):
    """
    Generates a true 3D/2D parametric CAD model using FreeCAD 1.1.3 Headless Engine.
    Includes auto-extraction of FreeCAD AppImage and graceful fallback so Streamlit never crashes.
    """
    os.makedirs("assets", exist_ok=True)
    temp_json = os.path.abspath("assets/temp_geojson_fc.json")
    script_path = os.path.abspath("assets/freecad_script.py")
    abs_fcstd = os.path.abspath(output_fcstd)
    abs_step = os.path.abspath(output_step)

    # 1. Locate or extract FreeCAD executable
    app_run = "./squashfs-root/AppRun"
    if not os.path.exists(app_run):
        # Attempt to extract bin/FreeCAD.AppImage if present
        if os.path.exists("bin/FreeCAD.AppImage"):
            try:
                os.chmod("bin/FreeCAD.AppImage", 0o755)
                subprocess.run(["./bin/FreeCAD.AppImage", "--appimage-extract"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    if not os.path.exists(app_run):
        # Fallback to system freecadcmd if installed
        app_run = "freecadcmd"

    with open(temp_json, "w") as f:
        json.dump(geojson_data, f)

    script_content = f"""import sys
import os
import json
import FreeCAD
import Part

with open(r"{temp_json}", "r") as f:
    geojson = json.load(f)

doc = FreeCAD.newDocument("BIM_Structural_Model")

features = geojson.get("features", [])

# 1. Generate RC Columns (300mm x 300mm x 3000mm)
nodes = [feat for feat in features if feat.get("properties", {{}}).get("type") == "node"]
for idx, n in enumerate(nodes, 1):
    coords = n["geometry"]["coordinates"]
    x_mm = coords[0] * 1000.0 - 150.0
    y_mm = coords[1] * 1000.0 - 150.0
    
    col = doc.addObject("Part::Box", f"Column_C{{idx}}")
    col.Placement.Base = FreeCAD.Vector(x_mm, y_mm, 0)
    col.Length = 300
    col.Width = 300
    col.Height = 3000

# 2. Generate Structural Beams (300mm x 600mm)
beams = [feat for feat in features if feat.get("properties", {{}}).get("type") == "beam"]
for b_idx, b in enumerate(beams, 1):
    coords = b["geometry"]["coordinates"]
    p1, p2 = coords[0], coords[1]
    x1, y1 = p1[0]*1000.0, p1[1]*1000.0
    x2, y2 = p2[0]*1000.0, p2[1]*1000.0
    
    length = ((x2-x1)**2 + (y2-y1)**2)**0.5
    if length < 10:
        continue
        
    beam = doc.addObject("Part::Box", f"Beam_B{{b_idx}}")
    beam.Placement.Base = FreeCAD.Vector(x1, y1, 2400)
    beam.Length = length
    beam.Width = 300
    beam.Height = 600

# 3. Save FreeCAD FCStd and STEP formats
doc.recompute()
doc.saveAs(r"{abs_fcstd}")
Part.export(doc.Objects, r"{abs_step}")
print("FREECAD CAD EXPORT GENERATED SUCCESSFULLY!")
"""

    with open(script_path, "w") as f:
        f.write(script_content)

    # 2. Safely execute FreeCAD script with offscreen Qt platform
    try:
        cmd = [app_run, script_path]
        env_vars = dict(os.environ)
        env_vars["QT_QPA_PLATFORM"] = "offscreen"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env_vars)
    except Exception as e:
        print(f"FreeCAD execution notice: {e}")

    # Clean up temp script files
    if os.path.exists(script_path):
        os.remove(script_path)
    if os.path.exists(temp_json):
        os.remove(temp_json)

    return output_fcstd, output_step

import re
import requests

def generate_parametric_freecad_script(user_prompt: str) -> str:
    """
    Parametrically generates a 2D FreeCAD Python script in mm units
    tailored to the user's natural language home description.
    """
    dims = re.findall(r'(\d+)\s*(?:ft|feet|m|meter)?\s*x\s*(\d+)', user_prompt.lower())
    if dims:
        w_ft = float(dims[0][0])
        l_ft = float(dims[0][1])
        W = w_ft * 304.8 if w_ft < 100 else w_ft
        L = l_ft * 304.8 if l_ft < 100 else l_ft
    else:
        W = 9144.0   # 30 ft in mm
        L = 15240.0  # 50 ft in mm

    return f"""# FreeCAD 2D Architectural Script — Generated from user prompt
# Description: {user_prompt.strip()}
# Dimensions: {W/304.8:.1f} ft x {L/304.8:.1f} ft ({W:.1f} mm x {L:.1f} mm)

import FreeCAD as App
import Part

doc = App.newDocument("Building_Plan_BM20")

W = {W:.1f}
L = {L:.1f}

def create_line(doc, name, p1, p2):
    line = Part.makeLine(App.Vector(*p1), App.Vector(*p2))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = line
    return obj

def create_wire(doc, name, points):
    vectors = [App.Vector(*pt) for pt in points]
    poly = Part.makePolygon(vectors)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = poly
    return obj

# 1. Main Building Footprint Boundary
create_wire(doc, "Outer_Boundary", [
    (0, 0, 0), (W, 0, 0), (W, L, 0), (0, L, 0), (0, 0, 0)
])

# 2. Architectural Room Partition Dividers
y1 = L * 0.16  # Veranda / Entry Foyer Line
y2 = L * 0.46  # Grand Living & Reception Room Rear Wall
y3 = L * 0.70  # Central Dining & Kitchen Divider Wall
x_mid = W * 0.50
x_bath = W * 0.75

create_line(doc, "Wall_Veranda_Foyer", (0, y1, 0), (W, y1, 0))
create_line(doc, "Wall_Living_Rear", (0, y2, 0), (W, y2, 0))
create_line(doc, "Wall_Dining_Kitchen_Rear", (0, y3, 0), (W, y3, 0))
create_line(doc, "Wall_Kitchen_Dining_Divider", (x_mid, y2, 0), (x_mid, y3, 0))
create_line(doc, "Wall_Bath_Partition", (x_bath, y2, 0), (x_bath, y3, 0))
create_line(doc, "Wall_Bedrooms_Central_Spine", (x_mid, y3, 0), (x_mid, L, 0))
create_line(doc, "Wall_Master_Suite_Divider", (0, L*0.86, 0), (x_mid, L*0.86, 0))
create_line(doc, "Wall_Guest_Bedroom_Divider", (x_mid, L*0.86, 0), (W, L*0.86, 0))

doc.recompute()
print("BM20 FreeCAD architectural script generated & recomputed successfully!")
"""

from core.kernel.synthesis import generate_spatial_script

def generate_freecad_script_from_prompt(user_prompt: str) -> str:
    """
    Converts a natural language home/building description into a valid 2D CAD Python script.
    Delegates to deep nested kernel module.
    """
    return generate_spatial_script(user_prompt)


