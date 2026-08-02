"""
core/freecad_script_runner.py
BM15: Runs a user-provided FreeCAD Python script headlessly via FreeCAD AppImage.
After the user script executes, injects a geometry-extraction pass that serialises
every 2D edge in the document to a JSON sidecar file.  That sidecar is then read by
bim_to_geojson.py to produce a structural GeoJSON without any AI / LLM call.
"""

import os
import json
import subprocess
import tempfile
import textwrap


# ── Locate FreeCAD executable ──────────────────────────────────────────────
def _find_freecad():
    """
    Probe known FreeCAD binary locations in priority order:
    1. squashfs-root/AppRun  (extracted AppImage — local dev)
    2. bin/FreeCAD.AppImage  (auto-extract if present — local dev)
    3. freecadcmd            (apt install freecad on Ubuntu/Streamlit Cloud)
    4. FreeCAD               (some Ubuntu package versions)
    5. freecad               (lowercase alias)
    """
    app_run = os.path.abspath("./squashfs-root/AppRun")

    # Try to extract AppImage if squashfs-root not yet extracted
    if not os.path.exists(app_run):
        for img in ["bin/FreeCAD.AppImage", "bin/FreeCAD_exec.AppImage"]:
            if os.path.exists(img):
                try:
                    os.chmod(img, 0o755)
                    subprocess.run(
                        [f"./{img}", "--appimage-extract"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
                break

    if os.path.exists(app_run):
        return app_run

    # Probe system-installed binaries (apt install freecad on Streamlit Cloud)
    import shutil
    for candidate in ["freecadcmd", "FreeCAD", "freecad", "/usr/bin/freecadcmd", "/usr/bin/FreeCAD"]:
        if shutil.which(candidate) or os.path.isfile(candidate):
            return candidate

    raise RuntimeError(
        "FreeCAD executable not found.\n"
        "• Local: place FreeCAD.AppImage in the bin/ folder\n"
        "• Streamlit Cloud: add 'freecad' to packages.txt (already done in this repo)"
    )


# ── Geometry extractor injected AFTER the user script ─────────────────────
# NOTE: uses __SIDECAR_PATH__ placeholder (not .format()) to avoid conflicts
# with curly braces inside the dict literals.
_EXTRACTOR = textwrap.dedent("""
import json as _json, FreeCAD as _FC, Part as _Part, os as _os

_out = []
_doc = _FC.ActiveDocument or _FC.newDocument("_empty")
_doc.recompute()

for _obj in _doc.Objects:
    _shape = getattr(_obj, "Shape", None)
    if _shape is None:
        continue
    for _edge in _shape.Edges:
        try:
            _v0 = _edge.Vertexes[0].Point
            _v1 = _edge.Vertexes[-1].Point
            if abs(_v0.z) > 1.0 and abs(_v1.z) > 1.0:
                continue
            scale = 0.001
            _row = dict(
                x1=round(_v0.x * scale, 4),
                y1=round(_v0.y * scale, 4),
                x2=round(_v1.x * scale, 4),
                y2=round(_v1.y * scale, 4),
                obj=_obj.Name,
                label=getattr(_obj, "Label", "")
            )
            _out.append(_row)
        except Exception:
            pass

_sidecar = r"__SIDECAR_PATH__"
with open(_sidecar, "w") as _f:
    _json.dump(_out, _f, indent=2)

print("[BM15] Extracted " + str(len(_out)) + " edges -> " + _sidecar)
""")


def run_freecad_script(user_script: str) -> list:
    """
    Execute *user_script* inside FreeCAD headlessly, then extract all 2-D edges.

    Returns a tuple (edges, stdout) where edges is a list of dicts:
        [{"x1": float, "y1": float, "x2": float, "y2": float,
          "obj": str, "label": str}, ...]

    Raises RuntimeError if FreeCAD execution fails.
    """
    os.makedirs("assets", exist_ok=True)
    sidecar_path = os.path.abspath("assets/bm15_edges.json")

    # Inject extractor after user script — use simple replace, not .format()
    extractor = _EXTRACTOR.replace("__SIDECAR_PATH__", sidecar_path.replace("\\", "/"))
    combined = user_script.rstrip() + "\n\n" + extractor

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="assets"
    ) as tmp:
        tmp.write(combined)
        script_path = tmp.name

    freecad_exe = _find_freecad()

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    try:
        result = subprocess.run(
            [freecad_exe, script_path],
            capture_output=True,
            text=True,
            timeout=420,
            env=env,
        )
        stdout = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "FreeCAD script execution timed out after 420 s. "
            "The FreeCAD AppImage cold-start requires ~5 minutes on first run. "
            "Please try again — subsequent runs are faster."
        )
    except FileNotFoundError:
        raise RuntimeError(
            "FreeCAD executable not found. "
            "Place FreeCAD.AppImage in the bin/ folder or install freecadcmd system-wide."
        )
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass

    if not os.path.exists(sidecar_path):
        raise RuntimeError(
            f"FreeCAD ran but produced no edge data.\n\nOutput:\n{stdout[:2000]}"
        )

    with open(sidecar_path) as f:
        edges = json.load(f)

    if not edges:
        raise RuntimeError(
            "FreeCAD script executed but no 2-D edges were found in the document. "
            "Make sure the script creates Part.Wire or Sketch objects in mm units."
        )

    return edges, stdout
