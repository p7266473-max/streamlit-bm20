try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

import numpy as np

def _create_box_mesh(x_min, x_max, y_min, y_max, z_min, z_max, color, opacity=1.0, name="Element"):
    """Generates 3D box vertices and faces for Plotly Mesh3d."""
    if not HAS_PLOTLY:
        return None
    x = [x_min, x_max, x_max, x_min, x_min, x_max, x_max, x_min]
    y = [y_min, y_min, y_max, y_max, y_min, y_min, y_max, y_max]
    z = [z_min, z_min, z_min, z_min, z_max, z_max, z_max, z_max]
    
    i = [7, 0, 0, 0, 4, 4, 2, 6, 4, 0, 3, 7]
    j = [4, 5, 1, 2, 5, 6, 3, 7, 6, 1, 2, 6]
    k = [0, 1, 2, 3, 6, 7, 7, 4, 7, 5, 6, 5]
    
    return go.Mesh3d(
        x=x, y=y, z=z,
        i=i, j=j, k=k,
        color=color,
        opacity=opacity,
        name=name,
        hovertext=name,
        hoverinfo="text",
        showscale=False
    )

def build_3d_bim_figure(geojson_data, num_floors=1):
    """
    Constructs an interactive 3D WebGL BIM Building Model for Streamlit dashboard visualization.
    Allows smooth 360-degree orbit rotation, zooming, panning, and structural element inspection.
    """
    if not HAS_PLOTLY:
        return None
        
    fig = go.Figure()
    
    features = geojson_data.get("features", [])
    
    # 1. 3D Pad Footings & Column Pillars
    nodes = [f for f in features if f.get("properties", {}).get("type") == "node"]
    for idx, n in enumerate(nodes, 1):
        coords = n["geometry"]["coordinates"]
        x, y = float(coords[0]), float(coords[1])
        
        # 3D Foundation Pad (1.2m x 1.2m x 0.35m)
        fnd_box = _create_box_mesh(
            x - 0.6, x + 0.6,
            y - 0.6, y + 0.6,
            -0.35, 0.0,
            color="#38BDF8", opacity=0.35,
            name=f"Pad Footing FND_{idx} (1.2x1.2m)"
        )
        fig.add_trace(fnd_box)
        
        # 3D RC Column (300mm x 300mm x 3000mm)
        col_h = 3.0 * num_floors
        col_box = _create_box_mesh(
            x - 0.15, x + 0.15,
            y - 0.15, y + 0.15,
            0.0, col_h,
            color="#EF4444", opacity=0.9,
            name=f"RC Column C{idx} (300x300mm)"
        )
        fig.add_trace(col_box)

    # 2. 3D Beams (Plinth Belt Beams at Z=0 and Roof Beams at Z=3.0)
    beams = [f for f in features if f.get("properties", {}).get("type") == "beam"]
    for b_idx, b in enumerate(beams, 1):
        coords = b["geometry"]["coordinates"]
        x1, y1 = float(coords[0][0]), float(coords[0][1])
        x2, y2 = float(coords[1][0]), float(coords[1][1])
        
        is_vert = abs(x1 - x2) < 0.1
        
        if is_vert:
            bx_min, bx_max = x1 - 0.15, x1 + 0.15
            by_min, by_max = min(y1, y2), max(y1, y2)
        else:
            bx_min, bx_max = min(x1, x2), max(x1, x2)
            by_min, by_max = y1 - 0.15, y1 + 0.15
            
        # Ground Plinth Belt Beam
        pb_box = _create_box_mesh(
            bx_min, bx_max, by_min, by_max,
            -0.1, 0.5,
            color="#F59E0B", opacity=0.75,
            name=f"Plinth Beam PB_{b_idx} (300x600mm)"
        )
        fig.add_trace(pb_box)
        
        # Roof Level Framing Beam
        rb_box = _create_box_mesh(
            bx_min, bx_max, by_min, by_max,
            2.5, 3.1,
            color="#10B981", opacity=0.85,
            name=f"Roof Beam RB_{b_idx} (300x600mm)"
        )
        fig.add_trace(rb_box)

    # 3. 3D Slab / Ground Plane
    pts = [f["geometry"]["coordinates"] for f in nodes]
    if pts:
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        slab = _create_box_mesh(
            min(xs) - 0.2, max(xs) + 0.2,
            min(ys) - 0.2, max(ys) + 0.2,
            -0.1, 0.0,
            color="#64748B", opacity=0.25,
            name="Ground Floor Slab (150mm C30)"
        )
        fig.add_trace(slab)

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="X (m)", showbackground=False, gridcolor="#334155", zerolinecolor="#475569"),
            yaxis=dict(title="Y (m)", showbackground=False, gridcolor="#334155", zerolinecolor="#475569"),
            zaxis=dict(title="Z (m)", showbackground=False, gridcolor="#334155", zerolinecolor="#475569"),
            aspectmode="data",
            dragmode="orbit"
        ),
        paper_bgcolor="rgba(15, 23, 42, 1.0)",
        plot_bgcolor="rgba(15, 23, 42, 1.0)",
        margin=dict(l=0, r=0, b=0, t=30),
        showlegend=False,
        hoverlabel=dict(
            bgcolor="#0F172A",
            bordercolor="#38BDF8",
            font_color="#F8FAFC",
            font_size=11,
            font_family="sans-serif"
        ),
        title=dict(text="INTERACTIVE 3D STRUCTURAL & BIM MODEL (360° ROTATABLE WebGL)", font=dict(color="#38BDF8", size=13))
    )
    
    return fig
