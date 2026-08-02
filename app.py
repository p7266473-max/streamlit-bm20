import os
import streamlit as st

from core import fields
from core.freecad_engine import generate_freecad_model, generate_freecad_script_from_prompt
from core.freecad_script_runner import run_freecad_script
from core.bim_to_geojson import edges_to_geojson
from core.viewer3d import build_3d_bim_figure
from core.assistant import chat_with_engineer
from generators import (
    generate_dxf_export, generate_pdf_report, render_dxf_to_png, export_drawing_to_pdf,
    generate_footing_report, generate_comprehensive_engineer_report
)

st.set_page_config(
    page_title="Spatial Core Solver — BM20",
    page_icon="🏗️",
    layout="wide"
)

import streamlit.components.v1 as components

st.markdown("""
<style>
/* Hide Streamlit top header, toolbar, GitHub fork badges, menu, and decoration */
#MainMenu {visibility: hidden !important; display: none !important;}
header {visibility: hidden !important; display: none !important;}
[data-testid="stHeader"] {visibility: hidden !important; display: none !important;}
[data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
[data-testid="stDecoration"] {visibility: hidden !important; display: none !important;}
[data-testid="stStatusWidget"] {visibility: hidden !important; display: none !important;}
.stAppDeployButton {visibility: hidden !important; display: none !important;}
#stDecoration {visibility: hidden !important; display: none !important;}

/* Hide Streamlit bottom footer and viewer/host badges */
footer {visibility: hidden !important; display: none !important;}
[data-testid="stFooter"] {visibility: hidden !important; display: none !important;}
.viewerBadge_container__16g3m {visibility: hidden !important; display: none !important;}
[class*="viewerBadge"] {visibility: hidden !important; display: none !important;}
[class*="styles_viewerBadge"] {visibility: hidden !important; display: none !important;}
[class*="ViewerBadge"] {visibility: hidden !important; display: none !important;}
.stActionButton {visibility: hidden !important; display: none !important;}
</style>
""", unsafe_allow_html=True)

# Continuous JS cleaner targeting both frame and parent DOM
components.html("""
<script>
function cleanupStreamlitUI() {
    const targetSelectors = [
        'footer', '[data-testid="stFooter"]', '[data-testid="stDecoration"]',
        '[data-testid="stStatusWidget"]', '[data-testid="stToolbar"]', '#MainMenu',
        'header', '.stAppDeployButton', '#stDecoration', '.viewerBadge_container__16g3m',
        '[class*="viewerBadge"]', '[class*="styles_viewerBadge"]', '[class*="ViewerBadge"]',
        '.stActionButton', 'button[title*="Streamlit"]', 'div[class*="StatusWidget"]'
    ];

    [document, window.parent.document].forEach(doc => {
        try {
            targetSelectors.forEach(selector => {
                doc.querySelectorAll(selector).forEach(el => {
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('visibility', 'hidden', 'important');
                    el.style.setProperty('opacity', '0', 'important');
                });
            });
        } catch (err) {}
    });
}
cleanupStreamlitUI();
setInterval(cleanupStreamlitUI, 250);
</script>
""", height=0, width=0)

st.markdown("""
<div style="background-color:#0F172A;padding:24px;border-radius:12px;border-bottom:4px solid #0284C7;margin-bottom:24px">
    <h1 style="color:white;margin:0;font-size:2.2rem">🏗️ Spatial Core Solver — BM20</h1>
    <p style="color:#94A3B8;margin:6px 0 0 0;font-size:1.1rem">
        Describe your design requirements → Geometry compilation → Verification engine execution.
    </p>
    <p style="color:#64748B;margin:10px 0 0 0;font-size:0.85rem">
        Spatial calculation dashboard demo.
    </p>
</div>
""", unsafe_allow_html=True)

# Top Navigation Buttons (Only visible AFTER pipeline execution completes)
if st.session_state.get("processed"):
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        st.markdown('<a href="#professional-deliverables" target="_self" style="text-decoration:none;"><div style="background-color:#0284C7; color:white; padding:9px 14px; border-radius:6px; text-align:center; font-weight:600; font-size:0.92rem;">📥 Jump to Deliverables</div></a>', unsafe_allow_html=True)
    with top_col2:
        st.markdown('<a href="#structural-assistant" target="_self" style="text-decoration:none;"><div style="background-color:#1E293B; color:white; padding:9px 14px; border-radius:6px; text-align:center; font-weight:600; font-size:0.92rem; border:1px solid #334155;">💬 Talk to Systems Assistant</div></a>', unsafe_allow_html=True)

values, _missing = fields.collect()

col1, col2, col3 = st.columns([1.2, 1.6, 1.2])

with col1:
    st.subheader("Step 1: Input Requirements Description")

    st.markdown("---")
    st.markdown("**Construction Parameter Configuration**")
    num_floors = st.radio(
        "How many floors do you want to construct?", [1, 2], index=0,
        help="Specifying 2 floors doubles the design load vectors."
    )

    st.markdown("---")
    st.markdown("**💬 Describe your intended home or floor plan layout**")
    st.caption(
        "Simply describe your desired house or room arrangement in plain text. "
        "Our system will compile your description, generate core geometry coordinates, "
        "and execute headless structural validation."
    )

    sample_user_prompt = (
        "A 2-story luxury residence with 5 rooms: Living Room, Master Suite, Kitchen, "
        "Dining Hall, and Guest Bedroom. Overall footprint 30ft x 50ft."
    )

    user_home_prompt = st.text_area(
        label="Natural Language Home / Floor Plan Description",
        value=sample_user_prompt,
        height=180,
        help="Enter details such as room types, footprint size, or floor arrangement.",
        key="user_home_prompt_input"
    )

    run_btn = st.button(
        "⚡ Compile Model & Run Verification Engine",
        type="primary",
        use_container_width=True
    )

    if st.session_state.get("processed"):
        st.markdown('<a href="#professional-deliverables" target="_self"><button style="width:100%; padding:9px; margin-top:10px; background-color:#0284C7; color:white; border:none; border-radius:6px; font-weight:600; cursor:pointer;">📥 Jump to Deliverables</button></a>', unsafe_allow_html=True)
        st.markdown('<a href="#structural-assistant" target="_self"><button style="width:100%; padding:9px; margin-top:6px; background-color:#1E293B; color:white; border:1px solid #334155; border-radius:6px; font-weight:600; cursor:pointer;">💬 Talk to Systems Assistant</button></a>', unsafe_allow_html=True)

if run_btn:
    if not user_home_prompt.strip():
        st.error("Please provide a description of your intended home or floor plan.")
    else:
        st.info("🤖 **Interpreting requirements prompt → Compiling spatial coordinates → Solving calculation matrix...**")
        with st.spinner("🔧 Compiling geometry coordinates → running verification matrix solver..."):
            try:
                # 1. AI generation of geometry script
                fc_script = generate_freecad_script_from_prompt(user_home_prompt)

                # 2. Execute generated script headlessly
                edges, fc_log = run_freecad_script(fc_script)
                geojson_data = edges_to_geojson(edges)

                # 3. Solve spatial calculation matrix
                from solver_frame3dd import run_frame3dd_analysis
                solver_res = run_frame3dd_analysis(geojson_data)

                iteration_log = [
                    "Prompt interpreter parsed requirements successfully.",
                    f"Spatial geometry engine extracted {len(edges)} geometry edges.",
                    "Topology compiler finished processing geometry components.",
                    "System verification calculation matrix solved successfully.",
                ]
                loop_success = True

                check1 = __import__("verify_checkpoints", fromlist=["verify_geometry_equilibrium"]).verify_geometry_equilibrium(geojson_data, solver_res)
                check2 = __import__("verify_checkpoints", fromlist=["verify_tributary_loads"]).verify_tributary_loads(geojson_data, solver_res)
                check3 = __import__("verify_checkpoints", fromlist=["verify_material_detailing"]).verify_material_detailing(solver_res)

                os.makedirs("assets", exist_ok=True)
                dxf_path           = os.path.join("assets", "structural_layout.dxf")
                png_path            = os.path.join("assets", "structural_drawing_all.png")
                pdf_path            = os.path.join("assets", "structural_compliance_report.pdf")
                drawing_pdf_path    = os.path.join("assets", "drawing_layout.pdf")
                footing_pdf_path    = os.path.join("assets", "structural_footing_advisory.pdf")
                comp_pdf_path       = os.path.join("assets", "comprehensive_structural_engineer_report.pdf")

                generate_dxf_export(geojson_data, dxf_path)
                render_dxf_to_png(geojson_data, os.path.join("assets", "structural_drawing_all.png"), layer_type="all")
                render_dxf_to_png(geojson_data, os.path.join("assets", "structural_drawing_arch.png"), layer_type="arch_plan")
                render_dxf_to_png(geojson_data, os.path.join("assets", "structural_drawing_foundation.png"), layer_type="foundation")
                render_dxf_to_png(geojson_data, os.path.join("assets", "structural_drawing_belt.png"), layer_type="belt_beam")
                render_dxf_to_png(geojson_data, os.path.join("assets", "structural_drawing_roof.png"), layer_type="roof_beam")

                export_drawing_to_pdf(geojson_data, drawing_pdf_path)
                generate_pdf_report(solver_res, check1, check2, check3, pdf_path)
                generate_footing_report(geojson_data, footing_pdf_path)
                generate_comprehensive_engineer_report(solver_res, check1, check2, check3, geojson_data, fc_script, comp_pdf_path)

                fcstd_path, step_path = generate_freecad_model(geojson_data)

                st.session_state["generated_fc_script"] = fc_script
                st.session_state["geojson_data"]        = geojson_data
                st.session_state["check1"]              = check1
                st.session_state["check2"]              = check2
                st.session_state["check3"]              = check3
                st.session_state["dxf_path"]            = dxf_path
                st.session_state["png_path"]            = png_path
                st.session_state["pdf_path"]            = pdf_path
                st.session_state["drawing_pdf_path"]    = drawing_pdf_path
                st.session_state["footing_pdf_path"]    = footing_pdf_path
                st.session_state["comp_pdf_path"]       = comp_pdf_path
                st.session_state["fcstd_path"]          = fcstd_path
                st.session_state["step_path"]           = step_path
                st.session_state["iteration_log"]       = iteration_log
                st.session_state["loop_success"]        = loop_success
                st.session_state["fc_log"]              = fc_log
                st.session_state["processed"]           = True
                st.rerun()
            except Exception as e:
                st.error(f"{str(e)}")

if st.session_state.get("processed"):
    check1 = st.session_state["check1"]
    check2 = st.session_state["check2"]
    check3 = st.session_state["check3"]
    geojson_data = st.session_state["geojson_data"]
    iteration_log = st.session_state["iteration_log"]
    loop_success = st.session_state["loop_success"]

    with col2:
        st.subheader("Step 2: Analytical Compliance Checkpoints")

        st.markdown("**🔧 Pipeline Execution Summary**")
        st.success(
            "✅ **Step 1:** Spatial coordinates interpreted & compiled successfully\n\n"
            "✅ **Step 2:** Structural topology extraction completed\n\n"
            "✅ **Step 3:** Calculation matrix solved"
        )

        st.markdown("---")
        st.info(f"**Checkpoint 1: Spatial Geometry & Global Equilibrium**\n\n{check1['summary']}")
        st.json(check1["metrics"])

        st.success(f"**Checkpoint 2: Tributary Loads & Load Paths**\n\n{check2['summary']}")
        st.write(check2["data"])

        c3_status = st.warning if not check3["passed"] else st.success
        c3_status(f"**Checkpoint 3: Detailing & Capacity Limits**\n\n{check3['summary']}")
        st.write(check3["data"])

        if iteration_log:
            st.markdown("**Compilation Steps**")
            for entry in iteration_log:
                st.write(f"✔ {entry}")

    with col3:
        st.subheader("Step 3: Rendering & Deliverables")

        st.markdown("**Select View Mode / Drawing Sheet**")
        view_tab = st.radio(
            "Select View Mode", 
            [
                "🌐 3D Interactive Design Model (360° Rotatable)",
                "A-01: 2D Spatial Floor Plan Layout",
                "S-01: Foundation Placement Plan", 
                "S-02: Base Ring Beam Plan", 
                "S-03: Upper Floor Slab Beam Plan", 
                "Combined Spatial Overlay"
            ],
            index=0,
            horizontal=False
        )
        
        if view_tab == "🌐 3D Interactive Design Model (360° Rotatable)":
            st.info("🎮 **3D WEBGL MODEL ACTIVE**: Click and drag anywhere on the 3D model below to rotate 360°, scroll to zoom, and inspect columns & beams!")
            fig_3d = build_3d_bim_figure(geojson_data, num_floors=num_floors)
            if fig_3d is not None:
                st.plotly_chart(fig_3d, use_container_width=True, key="bim_3d_viewer")
            else:
                st.warning("3D Viewer requires 'plotly'. Installing dependencies...")
        else:
            img_map = {
                "A-01: 2D Spatial Floor Plan Layout": ("assets/structural_drawing_arch.png", "A-01: 2D Spatial Floor Plan Layout"),
                "S-01: Foundation Placement Plan": ("assets/structural_drawing_foundation.png", "S-01: Foundation Pad Layout"),
                "S-02: Base Ring Beam Plan": ("assets/structural_drawing_belt.png", "S-02: Base / Plinth Level Grid Layout"),
                "S-03: Upper Floor Slab Beam Plan": ("assets/structural_drawing_roof.png", "S-03: Upper Floor Framing Layout Plan"),
                "Combined Spatial Overlay": ("assets/structural_drawing_all.png", "Combined Layout Overlay"),
            }
            target_img, caption_text = img_map[view_tab]
            if os.path.exists(target_img):
                st.image(target_img, caption=caption_text, use_container_width=True)

        st.markdown('<div id="professional-deliverables"></div>', unsafe_allow_html=True)
        st.subheader("Core System Deliverables & Reports")

        if "comp_pdf_path" in st.session_state and os.path.exists(st.session_state["comp_pdf_path"]):
            with open(st.session_state["comp_pdf_path"], "rb") as comp_file:
                st.download_button(
                    label="📄 Download Executive Synthesis Report (PDF)",
                    data=comp_file,
                    file_name="executive_synthesis_report.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

        with open(st.session_state["dxf_path"], "rb") as dxf_file:
            st.download_button(
                label="📥 Download Spatial Vector Layout (DXF)",
                data=dxf_file,
                file_name="spatial_layout.dxf",
                mime="application/dxf",
                use_container_width=True
            )

        with open(st.session_state["drawing_pdf_path"], "rb") as drawing_pdf_file:
            st.download_button(
                label="📥 Download Vector Blueprint (PDF)",
                data=drawing_pdf_file,
                file_name="spatial_blueprint.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        with open(st.session_state["pdf_path"], "rb") as pdf_file:
            st.download_button(
                label="📥 Download Analytical Compliance Matrix (PDF)",
                data=pdf_file,
                file_name="compliance_matrix.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        with open(st.session_state["footing_pdf_path"], "rb") as footing_file:
            st.download_button(
                label="📥 Download Spatial Implementation Schedule (PDF)",
                data=footing_file,
                file_name="implementation_schedule.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        if "fcstd_path" in st.session_state and os.path.exists(st.session_state["fcstd_path"]):
            with open(st.session_state["fcstd_path"], "rb") as fcstd_file:
                st.download_button(
                    label="📥 Download Core 3D CAD Geometry (.FCStd)",
                    data=fcstd_file,
                    file_name="geometry_core_model.FCStd",
                    mime="application/octet-stream",
                    use_container_width=True
                )

        if "step_path" in st.session_state and os.path.exists(st.session_state["step_path"]):
            with open(st.session_state["step_path"], "rb") as step_file:
                st.download_button(
                    label="📥 Download Spatial 3D STEP File (.STEP)",
                    data=step_file,
                    file_name="geometry_exchange_model.step",
                    mime="application/step",
                    use_container_width=True
                )

    # ── 💬 Interactive Systems Chat Assistant (Visible after processing) ──
    st.markdown('<div id="structural-assistant"></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("💬 Talk to Systems Assistant")
    st.caption(
        "Directly query the calculations using our interactive systems assistant. "
        "Ask about design compliance thresholds, layout spans, or loading capacity distributions."
    )

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": "Welcome. I have verified the spatial calculation results generated from your home description. Ask me any technical questions about the layout capacity or compliance thresholds."}
        ]

    chat_container = st.container(height=350)
    with chat_container:
        for message in st.session_state["chat_messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("Ask the systems assistant a question about this layout..."):
        with chat_container:
            st.session_state["chat_messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            current_state = {
                "freecad_script": st.session_state.get("generated_fc_script", "No script generated"),
                "geojson_data": st.session_state.get("geojson_data"),
                "check1": st.session_state.get("check1"),
                "check2": st.session_state.get("check2"),
                "check3": st.session_state.get("check3")
            }

            with st.chat_message("assistant"):
                with st.spinner("Analyzing calculation data..."):
                    response = chat_with_engineer(st.session_state["chat_messages"][1:], current_state)
                    st.markdown(response)
                    st.session_state["chat_messages"].append({"role": "assistant", "content": response})
        st.rerun()

else:
    with col2:
        st.info("Awaiting requirement description prompt & execution to run compliance checks.")
    with col3:
        st.info("Awaiting requirement description prompt & execution to compile deliverables.")
