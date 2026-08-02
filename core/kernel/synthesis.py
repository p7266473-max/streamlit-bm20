import re
import requests
from core.security.vault import get_api_endpoint, build_headers

def generate_parametric_script(user_prompt: str) -> str:
    dims = re.findall(r'(\d+)\s*(?:ft|feet|m|meter)?\s*x\s*(\d+)', user_prompt.lower())
    if dims:
        w_ft = float(dims[0][0])
        l_ft = float(dims[0][1])
        W = w_ft * 304.8 if w_ft < 100 else w_ft
        L = l_ft * 304.8 if l_ft < 100 else l_ft
    else:
        W = 9144.0   # 30 ft in mm
        L = 15240.0  # 50 ft in mm

    return f"""# Core Geometry Script — BM20
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

create_wire(doc, "Outer_Boundary", [(0,0,0), (W,0,0), (W,L,0), (0,L,0), (0,0,0)])

y1 = L * 0.16
y2 = L * 0.46
y3 = L * 0.70
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
"""

def generate_spatial_script(user_prompt: str) -> str:
    building_keywords = [
        "room", "home", "house", "villa", "floor", "plan", "building", "bedroom", 
        "living", "kitchen", "bath", "hall", "suite", "dimension", "ft", "meter", 
        "story", "layout", "wall", "plot", "residence", "architecture", "space", "design"
    ]
    
    is_building_query = any(k in user_prompt.lower() for k in building_keywords) or len(user_prompt.strip()) > 15
    if not is_building_query:
        raise ValueError(
            "Guardrail Notice: Please describe a building, home, or room floor plan layout "
            "(e.g., 'A 30ft x 50ft villa with 5 rooms: Living Room, Master Suite, Kitchen, Dining Hall, and Guest Bedroom')."
        )

    url = get_api_endpoint()
    headers = build_headers()

    system_instructions = """You are a Senior BIM Architectural Engineer specializing in FreeCAD CAD scripting.
Your task is to take a natural language description of a building or house floor plan and generate a complete, standalone, syntactically valid FreeCAD 2D Python script.

FREECAD SCRIPT REQUIREMENTS:
1. Native FreeCAD units MUST be millimeters (mm). (1 ft = 304.8 mm, 1 m = 1000 mm).
2. Must import FreeCAD as App and Part:
   import FreeCAD as App
   import Part
   doc = App.newDocument("Architectural_Plan")
3. Define plot width (W) and plot length (L) in mm based on user prompt or realistic defaults (e.g. 9144.0 mm x 15240.0 mm).
4. Helper functions create_wire and create_line using Part.makePolygon and Part.makeLine.
5. Create outer boundary polygon wire "Outer_Boundary".
6. Create interior room partition walls as Part Line / Wire features for all requested rooms (Living Room, Kitchen, Dining, Master Suite, Bedrooms, Baths, etc.).
7. End with doc.recompute().
8. Output ONLY raw executable Python code inside a ```python ``` block. No conversational prose.
"""

    payload = {
        "model": "deepseek-v4-flash-free",
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": f"Generate a FreeCAD 2D floor plan script for this building description: '{user_prompt}'"}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            if "```python" in content:
                script = content.split("```python")[1].split("```")[0].strip()
            elif "```" in content:
                script = content.split("```")[1].split("```")[0].strip()
            else:
                script = content.strip()
            if "import FreeCAD" in script and "doc.recompute()" in script:
                return script
    except Exception:
        pass

    return generate_parametric_script(user_prompt)
