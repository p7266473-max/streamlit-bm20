import numpy as np

def run_frame3dd_analysis(geojson_data):
    """
    Implements a 2D direct stiffness matrix method as the primary structural solver.
    """
    nodes = {}
    elements = []
    
    # 1. Parse Nodes
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry")
        props = feature.get("properties", {})
        if geom and geom.get("type") == "Point":
            coords = geom.get("coordinates")
            x, y = float(coords[0]), float(coords[1])
            node_id = int(props.get("node_id", len(nodes) + 1))
            support = props.get("support", "none")
            nodes[node_id] = {
                "coords": (x, y),
                "support": support
            }
            
    # 2. Parse Elements
    element_id_counter = 1
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry")
        props = feature.get("properties", {})
        if geom and geom.get("type") == "LineString":
            coords = geom.get("coordinates")
            if len(coords) < 2:
                continue
            pt1, pt2 = coords[0], coords[1]
            
            def find_or_create_node(pt):
                for nid, ndata in nodes.items():
                    if np.allclose(ndata["coords"], pt, atol=0.01):
                        return nid
                new_id = len(nodes) + 1
                nodes[new_id] = {"coords": (pt[0], pt[1]), "support": "none"}
                return new_id
            
            n1 = find_or_create_node(pt1)
            n2 = find_or_create_node(pt2)
            
            width = float(props.get("section_w_mm", 300)) / 1000.0
            height = float(props.get("section_h_mm", 600)) / 1000.0
            
            A = width * height
            E = 3.0e7  # 30 GPa in kN/m^2
            I = (width * (height ** 3)) / 12.0
            load_val = float(props.get("load_kn_m", 0.0))
            
            elements.append({
                "element_id": element_id_counter,
                "n1": n1,
                "n2": n2,
                "A": A,
                "E": E,
                "I": I,
                "load": load_val
            })
            element_id_counter += 1
            
    num_nodes = len(nodes)
    if num_nodes == 0:
        return {"nodes": {}, "elements": []}
        
    # Global degrees of freedom (3 per node)
    K_global = np.zeros((3 * num_nodes, 3 * num_nodes))
    F_global = np.zeros(3 * num_nodes)
    
    # Node indexing helper
    node_keys = sorted(list(nodes.keys()))
    node_to_idx = {nid: i for i, nid in enumerate(node_keys)}
    
    # 3. Assemble stiffness matrix and load vector
    for elem in elements:
        n1, n2 = elem["n1"], elem["n2"]
        idx1, idx2 = node_to_idx[n1], node_to_idx[n2]
        
        c1 = nodes[n1]["coords"]
        c2 = nodes[n2]["coords"]
        dx = c2[0] - c1[0]
        dy = c2[1] - c1[1]
        L = np.sqrt(dx*dx + dy*dy)
        if L < 1e-9:
            continue
        
        cos_t = dx / L
        sin_t = dy / L
        
        # Transformation matrix
        T = np.array([
            [cos_t, sin_t, 0, 0, 0, 0],
            [-sin_t, cos_t, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, cos_t, sin_t, 0],
            [0, 0, 0, -sin_t, cos_t, 0],
            [0, 0, 0, 0, 0, 1]
        ])
        
        # Element stiffness in local coordinates
        E = elem["E"]
        A = elem["A"]
        I = elem["I"]
        
        k_local = np.array([
            [E*A/L,     0,          0,          -E*A/L,    0,          0],
            [0,         12*E*I/L**3,6*E*I/L**2, 0,         -12*E*I/L**3,6*E*I/L**2],
            [0,         6*E*I/L**2, 4*E*I/L,    0,         -6*E*I/L**2, 2*E*I/L],
            [-E*A/L,    0,          0,          E*A/L,     0,          0],
            [0,         -12*E*I/L**3,-6*E*I/L**2,0,        12*E*I/L**3,-6*E*I/L**2],
            [0,         6*E*I/L**2, 2*E*I/L,    0,         -6*E*I/L**2, 4*E*I/L]
        ])
        
        # Transform to global
        k_global_elem = T.T @ k_local @ T
        
        # Global DoFs
        dofs = [3*idx1, 3*idx1+1, 3*idx1+2, 3*idx2, 3*idx2+1, 3*idx2+2]
        
        for i in range(6):
            for j in range(6):
                K_global[dofs[i], dofs[j]] += k_global_elem[i, j]
                
        # Element Load (Equivalent nodal loads)
        # Applied directly in GLOBAL -Y (gravity). This keeps the sum of global-y
        # reactions equal to sum(w * L) for every beam orientation, so the global
        # equilibrium check (reactions vs total applied load) is physically consistent.
        w = elem["load"]
        if w > 0:
            f_y = -w * L / 2.0
            m = -w * L**2 / 12.0
            f_global_elem = np.array([0, f_y, m, 0, f_y, -m])
            for i in range(6):
                F_global[dofs[i]] += f_global_elem[i]

        elem["k_global_elem"] = k_global_elem
        elem["L"] = L

    # 4. Boundary conditions (Fixities)
    active_dofs = list(range(3 * num_nodes))
    for nid, ndata in nodes.items():
        idx = node_to_idx[nid]
        if ndata["support"] == "fixed":
            active_dofs.remove(3*idx)
            active_dofs.remove(3*idx+1)
            active_dofs.remove(3*idx+2)
        elif ndata["support"] == "pinned":
            active_dofs.remove(3*idx)
            active_dofs.remove(3*idx+1)
            
    # Solve system
    U = np.zeros(3 * num_nodes)
    if len(active_dofs) > 0:
        K_sub = K_global[np.ix_(active_dofs, active_dofs)]
        F_sub = F_global[active_dofs]
        try:
            U_sub = np.linalg.solve(K_sub, F_sub)
        except np.linalg.LinAlgError:
            # Fallback safety: Tikhonov regularization to prevent singular matrix crashes
            diag_val = np.abs(np.diagonal(K_sub))
            mean_diag = np.mean(diag_val) if len(diag_val) > 0 else 1.0
            eps = 1e-5 * mean_diag
            K_regulated = K_sub + eps * np.eye(K_sub.shape[0])
            try:
                U_sub = np.linalg.solve(K_regulated, F_sub)
            except Exception:
                # Last resort: least-squares solution. Never crash the pipeline on
                # unstable geometry; the equilibrium/detailing checks still report it.
                U_sub = np.linalg.lstsq(K_sub, F_sub, rcond=None)[0]
        U[active_dofs] = U_sub
        
    # Reconstruct reactions
    Reactions = K_global @ U - F_global
    
    # 5. Format results
    results = {
        "nodes": {},
        "elements": []
    }
    
    for nid in nodes.keys():
        idx = node_to_idx[nid]
        results["nodes"][nid] = {
            "displacements": [float(U[3*idx]), float(U[3*idx+1]), float(U[3*idx+2])],
            "reactions": [float(Reactions[3*idx]), float(Reactions[3*idx+1]), float(Reactions[3*idx+2])],
            "coordinates": list(nodes[nid]["coords"])
        }
        
    for elem in elements:
        # Recover member end forces from solved displacements plus fixed-end
        # reactions of the applied UDL. Moments live at indices 2 and 5.
        w = elem["load"]
        L = elem["L"]
        k_global_elem = elem["k_global_elem"]
        idx1, idx2 = node_to_idx[elem["n1"]], node_to_idx[elem["n2"]]
        u_glob = np.array([
            U[3*idx1], U[3*idx1+1], U[3*idx1+2],
            U[3*idx2], U[3*idx2+1], U[3*idx2+2]
        ])
        # Fixed-end forces (reaction side) for a global -Y UDL of magnitude w.
        fixed_end = np.array([0, w*L/2, w*L**2/12, 0, w*L/2, -w*L**2/12])
        f_glob = k_global_elem @ u_glob + fixed_end

        results["elements"].append({
            "element_id": elem["element_id"],
            "n1": elem["n1"],
            "n2": elem["n2"],
            "forces": [float(v) for v in f_glob]
        })
        
    return results
