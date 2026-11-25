"""PipeForge: AI-assisted pipe bending and production engineering (Streamlit app).

Seven panels, all computed live by the pipeforge package from the chosen part:
part input, 3D CAD, bending program and DFM, springback, fixture and
station, line and kaizen, process sheet. STEP files need CadQuery; when it is
not installed (as on the free hosting), the pre-generated STEP files in
artifacts/ are served for the sample parts and the rest is computed live.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeforge import cad, kaizen, llm_assist  # noqa: E402
from pipeforge.drawing import DrawingInfo, make_drawing  # noqa: E402
from pipeforge.geometry import GeometryError  # noqa: E402
from pipeforge.line_sim import baseline_line, replicate, yamazumi  # noqa: E402
from pipeforge.materials import MATERIALS  # noqa: E402
from pipeforge.mesh import tube_mesh  # noqa: E402
from pipeforge.parts import Part, sample_parts  # noqa: E402
from pipeforge.pipeline import DEFAULT_SETUP, analyze, in_tubebend_domain, ml_springback_at_47  # noqa: E402
from pipeforge.process_sheet import write_excel, write_pdf  # noqa: E402
from pipeforge.station import TRANSITIONS, Inputs, Station  # noqa: E402

ART = ROOT / "artifacts"
INK, ORANGE, MUTED, STEEL = "#16181B", "#E8501A", "#5B6068", "#9AA3AD"

st.set_page_config(page_title="PipeForge", page_icon="🔧", layout="wide")

# ------------------------------------------------------------------ labels (EN / 日本語)
L = {
    "title": ("PipeForge", "PipeForge"),
    "subtitle": ("AI-assisted pipe bending & production engineering", "AIを活用したパイプ曲げ・生産技術の検討"),
    "part": ("Part", "部品"),
    "tab_cad": ("3D CAD & drawing", "3D CAD・図面"),
    "tab_prog": ("Bending program & DFM", "曲げプログラム・製造性"),
    "tab_sb": ("Springback (ML)", "スプリングバック（ML）"),
    "tab_fx": ("Fixture & station", "検査治具・ステーション"),
    "tab_line": ("Line & kaizen", "ライン・改善"),
    "tab_sheet": ("Process sheet", "工程表"),
    "sample": ("Sample part", "サンプル部品"),
    "custom": ("Custom XYZ", "XYZ入力"),
    "material": ("Material (JIS)", "材質（JIS）"),
    "cut": ("Cut length", "切断長"),
    "bends": ("Bends", "曲げ数"),
    "sb_model": ("Springback model", "スプリングバックモデル"),
    "takt": ("Takt time", "タクトタイム"),
    "oee": ("OEE", "設備総合効率（OEE）"),
    "yamazumi": ("Yamazumi (work content vs takt)", "山積み表（作業量とタクト）"),
    "download": ("Download", "ダウンロード"),
}
with st.sidebar:
    lang = st.radio("Language / 言語", ["EN", "日本語"], horizontal=True)
JA = lang == "日本語"


def t(key: str) -> str:
    en, ja = L[key]
    return f"{ja}" if JA else en


# ------------------------------------------------------------------ cached computations


@st.cache_data(show_spinner=False)
def samples() -> dict[str, dict]:
    return {k: v.to_dict() for k, v in sample_parts().items()}


@st.cache_data(show_spinner=False)
def read_json(rel: str) -> dict | list | None:
    p = ART / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


@st.cache_data(show_spinner=False)
def mesh_of(part_d: dict, segments: int = 28):
    part = Part.from_dict(part_d)
    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=segments, step_deg=4.0)
    return m.vertices, m.faces


@st.cache_data(show_spinner=False)
def stl_bytes(part_d: dict) -> bytes:
    import tempfile

    part = Part.from_dict(part_d)
    with tempfile.TemporaryDirectory() as td:
        buf = Path(td) / "p.stl"
        tube_mesh(part.points, part.clr, part.od, part.wall, segments=48, step_deg=2.0).write_stl(buf, part.part_no)
        return buf.read_bytes()


@st.cache_data(show_spinner=False)
def drawing_pdf(part_d: dict) -> bytes:
    part = Part.from_dict(part_d)
    pdf = io.BytesIO()
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.pdf"
        make_drawing(part.points, part.clr, DrawingInfo(part.part_no, part.name, part.material, part.od, part.wall), p)
        pdf.write(p.read_bytes())
    return pdf.getvalue()


@st.cache_data(show_spinner=False)
def drawing_png(part_d: dict) -> bytes:
    part = Part.from_dict(part_d)
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.png"
        make_drawing(part.points, part.clr, DrawingInfo(part.part_no, part.name, part.material, part.od, part.wall),
                     svg_path=None, pdf_path=p)
        return p.read_bytes()


def run_analysis(part_d: dict, mode: str, measured: float | None, setup: dict | None):
    return analyze(Part.from_dict(part_d), mode, ml_setup=setup, measured_per_90=measured)


# ------------------------------------------------------------------ part input (sidebar)

with st.sidebar:
    st.markdown(f"### {t('part')}")
    # Stable keys and option values: translated labels must not reset the user's choices.
    src = st.radio(" ", ["sample", "custom"], format_func=t, horizontal=True, label_visibility="collapsed", key="src")
    smp = samples()
    if src == "sample":
        names = {f"{k}  {v['name']}": k for k, v in smp.items()}
        pick = st.selectbox(t("sample"), list(names), index=list(smp).index("PF-HB-2201"), key="sample_pick")
        part_d = smp[names[pick]]
    else:
        default = "\n".join(", ".join(f"{c:g}" for c in p) for p in smp["PF-HB-2201"]["points"])
        txt = st.text_area("XYZ intersection points (mm), one per line: x, y, z", default, height=170)
        c1, c2, c3 = st.columns(3)
        od = c1.number_input("OD (mm)", 3.0, 60.0, 22.2, 0.1)
        wall = c2.number_input("t (mm)", 0.3, 6.0, 1.6, 0.1)
        clr = c3.number_input("CLR (mm)", 3.0, 400.0, 60.0, 1.0)
        mat = st.selectbox(t("material"), list(MATERIALS), index=1, key="material")
        try:
            pts = [[float(x) for x in line.replace(";", ",").split(",")] for line in txt.strip().splitlines() if line.strip()]
            part_d = Part(part_no="CUSTOM-01", name="Custom part", material=mat, od=od, wall=wall, clr=clr,
                          points=np.array(pts)).to_dict()
        except (GeometryError, ValueError) as exc:
            st.error(f"Geometry problem: {exc}")
            st.stop()
    part = Part.from_dict(part_d)
    st.caption(f"{part.material} · OD {part.od:g} x t {part.wall:g} mm · CLR {', '.join(f'{r:g}' for r in sorted(set(part.radii)))}"
               f" · {part.n_bends} {t('bends').lower()}")
    st.markdown(f"### {t('sb_model')}")
    modes = ["ml", "physics", "measured", "none"]
    default_mode = 0 if in_tubebend_domain(part) else 1
    mode = st.selectbox(t("sb_model"), modes, index=default_mode, label_visibility="collapsed",
                        format_func={"ml": "ML (TubeBEND)", "physics": "Physics estimate", "measured": "Measured (trial bends)",
                                     "none": "None"}.get)
    measured = st.number_input("Springback per 90° (deg)", 0.0, 20.0, 1.5, 0.1) if mode == "measured" else None
    st.divider()
    st.caption("Self-directed engineering study. Sample parts and the line model are synthetic; physics values are "
               "engineering estimates; the ML model is trained on TubeBEND (CC BY 4.0). Not a Yamato or customer part.")

try:
    A = run_analysis(part_d, mode, measured, None)
except (GeometryError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

# ------------------------------------------------------------------ header

st.markdown(f"## {t('title')}  \n{t('subtitle')}")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(t("part"), part.part_no)
m2.metric(t("bends"), part.n_bends)
m3.metric(t("cut"), f"{A.ybc.cut_length:.1f} mm")
m4.metric("DFM", A.dfm.status.upper(), f"{A.dfm.counts()['warn']} warn · {A.dfm.counts()['fail']} fail", delta_color="off")
m5.metric(t("sb_model"), A.springback_model)

tabs = st.tabs([t("tab_cad"), t("tab_prog"), t("tab_sb"), t("tab_fx"), t("tab_line"), t("tab_sheet")])


def tube_fig(part_d: dict, height: int = 520) -> go.Figure:
    v, f = mesh_of(part_d)
    fig = go.Figure(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=STEEL,
                              flatshading=False, lighting=dict(ambient=0.45, diffuse=0.8, specular=0.6, roughness=0.35),
                              name="tube", hoverinfo="skip"))
    p = Part.from_dict(part_d)
    fig.add_trace(go.Scatter3d(x=p.points[:, 0], y=p.points[:, 1], z=p.points[:, 2], mode="lines+markers+text",
                               line=dict(color=ORANGE, width=2, dash="dot"), marker=dict(size=3, color=ORANGE),
                               text=[f"P{i}" for i in range(len(p.points))], textfont=dict(size=10, color=INK),
                               name="XYZ intersection points"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                      scene=dict(aspectmode="data", xaxis_title="X mm", yaxis_title="Y mm", zaxis_title="Z mm"))
    return fig


# ------------------------------------------------------------------ 1. CAD and drawing
with tabs[0]:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(tube_fig(part_d), width="stretch")
    with c2:
        st.markdown("**Parametric 3D CAD**: annulus swept along lines and true arcs. STEP from CadQuery; STL and the "
                    "drawing are generated live from the same centerline.")
        step_file = ART / "parts" / part.part_no / f"{part.part_no}.step"
        if cad.available():
            import tempfile

            with tempfile.TemporaryDirectory() as td:
                sp = Path(td) / "p.step"
                cad.export(cad.tube_solid(part.points, part.clr, part.od, part.wall), sp)
                st.download_button(f"{t('download')} STEP", sp.read_bytes(), f"{part.part_no}.step")
        elif step_file.exists():
            st.download_button(f"{t('download')} STEP (pre-generated)", step_file.read_bytes(), step_file.name)
        else:
            st.info("STEP needs CadQuery (run locally: `make setup`); STL and PDF below work everywhere.")
        st.download_button(f"{t('download')} STL", stl_bytes(part_d), f"{part.part_no}.stl")
        st.download_button(f"{t('download')} drawing PDF (A3)", drawing_pdf(part_d), f"{part.part_no}_drawing.pdf")
        st.dataframe(pd.DataFrame(part.points, columns=["X", "Y", "Z"]).rename_axis("P").round(2), height=250)
    st.image(drawing_png(part_d), caption="A3 drawing: third-angle views, bend table, title block (generated)")

# ------------------------------------------------------------------ 2. Bending program and DFM
with tabs[1]:
    st.markdown(f"**{t('sb_model')}:** {A.springback_note}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Nominal LRA** (part geometry)")
        lra = pd.DataFrame(A.lra)
        lra["bend"] = lra["bend"].replace(0, "end")
        st.dataframe(lra.round(3), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Compensated YBC** (what the bender runs)")
        st.dataframe(pd.DataFrame(A.ybc.as_table()), hide_index=True, width="stretch")
    st.caption(f"C = A + springback (overbend). Y is shortened by the tangent growth that springback causes "
               f"(radius grows at constant arc length), so the intersection points land on nominal. Cut length "
               f"{A.ybc.cut_length:.1f} mm (program) vs {A.cut_length_nominal:.1f} mm (nominal geometry).")
    buf = io.StringIO()
    buf.write("BEND,Y,B,C\n" + "\n".join(f"{r.bend},{r.Y:.2f},{r.B:.2f},{r.C:.2f}" for r in A.ybc.rows)
              + f"\nEND,{A.ybc.final_Y:.2f},,\n")
    st.download_button(f"{t('download')} YBC program (.csv)", buf.getvalue(), f"{part.part_no}_ybc.csv")
    st.markdown(f"**Manufacturability (DFM)**: {A.dfm.status.upper()} · bend sequence: {A.dfm.sequence} · "
                f"tooling: {A.dfm.tooling.get('class', '')}")
    icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    dfm = pd.DataFrame(A.dfm.as_rows())
    dfm.insert(0, "", dfm["status"].map(icons))
    st.dataframe(dfm.drop(columns=["status"]), hide_index=True, width="stretch", height=420)
    st.markdown("**Per-bend estimates** (engineering estimates; see ENGINEERING_NOTES)")
    st.dataframe(pd.DataFrame(A.bends), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 3. Springback
with tabs[2]:
    met = read_json("springback/metrics.json")
    cl = read_json("springback/closed_loop.json")
    meta = read_json("springback/model_meta.json")
    if not met:
        st.warning("Run `make train` to create the springback results.")
    else:
        st.markdown(f"**TubeBEND**: {met['n_runs']} real rotary-draw bends (318 recorded, 3 failed runs dropped), "
                    f"22 x 1 mm stainless, CLR 33 mm, 47° target, WAFIOS RBV 35 (Oz et al., 2025, CC BY 4.0). "
                    f"Measured springback {met['target_mean']:.2f} ± {met['target_sd']:.2f}°.")
        best = met["springback"][met["best"]["setup"]]
        phys = met["physics"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("ML MAE, unseen setups", f"{best['mae']['mean']:.3f}°", f"± {best['mae']['sd']:.3f}", delta_color="off")
        c2.metric("R²", f"{best['r2']['mean']:.2f}", f"± {best['r2']['sd']:.2f}", delta_color="off")
        c3.metric("Physics estimate", f"{phys['mid']:.2f}°", f"band {phys['low']:.2f} to {phys['high']:.2f}", delta_color="off")
        c4.metric("Bends within ±0.5°", f"{100 * cl['fpy']['ml']:.1f}%", f"offset only {100 * cl['fpy']['offset']:.1f}%",
                  delta_color="off")
        st.caption("Scores are GroupKFold by machine setup (5 folds x 5 repeats): every prediction is for a setting "
                   "the model never saw. Random KFold would report lower errors because replicates leak across folds.")
        rows = []
        for k, v in met["springback"].items():
            if "note" in v:
                rows.append({"model | features": k, "MAE (deg)": round(v["mae"], 3), "RMSE": round(v["rmse"], 3), "R²": round(v["r2"], 2)})
            else:
                rows.append({"model | features": k, "MAE (deg)": f"{v['mae']['mean']:.3f} ± {v['mae']['sd']:.3f}",
                             "RMSE": f"{v['rmse']['mean']:.3f}", "R²": f"{v['r2']['mean']:.2f} ± {v['r2']['sd']:.2f}"})
        c1, c2 = st.columns([3, 2])
        with c1:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            oof = ART / "springback" / "oof_predictions.csv"
            if oof.exists():
                df = pd.read_csv(oof)
                key = met["best"]["setup"]
                fig = go.Figure()
                lo, hi = df["springback_deg"].min() - 0.1, df["springback_deg"].max() + 0.1
                fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=INK, width=1), name="ideal"))
                fig.add_trace(go.Scatter(x=df["springback_deg"], y=df[key], mode="markers",
                                         marker=dict(color=ORANGE, size=6, opacity=0.65), name=key))
                fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), title="Parity, out-of-fold",
                                  xaxis_title="measured springback (deg)", yaxis_title="predicted (deg)", showlegend=False)
                st.plotly_chart(fig, width="stretch")
        with c2:
            shap = read_json("springback/shap_importance_setup.json")
            if shap:
                s = pd.DataFrame(shap).head(7)[::-1]
                fig = go.Figure(go.Bar(x=s["mean_abs_shap_deg"], y=s["feature"], orientation="h", marker_color=ORANGE))
                fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="SHAP: mean |effect| (deg)")
                st.plotly_chart(fig, width="stretch")
            pol = {"none": "No compensation", "physics": "Physics estimate", "offset": "One constant offset",
                   "ml": "ML (setup)", "ml_in_process": "ML + process signals"}
            fig = go.Figure(go.Bar(x=[pol[k] for k in cl["fpy"]], y=[100 * v for v in cl["fpy"].values()],
                                   marker_color=[MUTED, MUTED, STEEL, ORANGE, ORANGE]))
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="% within ±0.5°",
                              title="Closed loop on real runs")
            st.plotly_chart(fig, width="stretch")
        st.markdown("**What-if: predict springback for a machine setup** (ML, valid for the TubeBEND tube only)")
        if meta:
            lv = meta["setup_levels"]
            cols = st.columns(4)
            setup = {k: cols[i].selectbox(k, lv[k], index=lv[k].index(DEFAULT_SETUP[k]) if DEFAULT_SETUP[k] in lv[k] else 0)
                     for i, k in enumerate(lv)}
            pred = ml_springback_at_47(setup)
            st.success(f"Predicted springback at 47°: **{pred:.2f}°** (90 % of held-out runs were within "
                       f"±{meta['interval90_deg']:.2f}° of the prediction). Die angle for 47°: **{47 + pred:.2f}°**.")
        st.caption("The textbook (elastic, perfectly plastic) estimate explains about a fifth of the measured springback "
                   "even at the tensile strength: machine and tooling effects the formula does not model dominate. "
                   "That gap is why shops use trial bends, and why a model that learns from process data helps.")

# ------------------------------------------------------------------ 4. Fixture and station
with tabs[3]:
    fx = A.fixture
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = go.Figure()
        v, f = mesh_of(part_d, 20)
        R, off = fx.rotation, fx.offset
        vv = (R @ v.T).T + off
        fig.add_trace(go.Mesh3d(x=vv[:, 0], y=vv[:, 1], z=vv[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2], color=STEEL,
                                opacity=1.0, name="tube", hoverinfo="skip"))

        def box(cx, cy, z0, lx, ly, h, yaw, color, name, opacity=1.0):  # type: ignore[no-untyped-def]
            c, s_ = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
            xs, ys = np.array([-1, 1, 1, -1, -1, 1, 1, -1]) * lx / 2, np.array([-1, -1, 1, 1, -1, -1, 1, 1]) * ly / 2
            zs = np.array([0, 0, 0, 0, 1, 1, 1, 1]) * h + z0
            X, Y = cx + c * xs - s_ * ys, cy + s_ * xs + c * ys
            fig.add_trace(go.Mesh3d(x=X, y=Y, z=zs, i=[7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2], j=[3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3],
                                    k=[0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6], color=color, opacity=opacity, name=name,
                                    hovertext=name, hoverinfo="text"))

        w, h, tt = fx.plate_size
        box((fx.plate_min[0] + fx.plate_max[0]) / 2, (fx.plate_min[1] + fx.plate_max[1]) / 2, -tt, w, h, tt, 0, "#8A9099", "plate")
        for b in fx.blocks:
            col = ORANGE if b.datum else "#E9E6DF"
            box(b.contact[0], b.contact[1], 0, b.length, b.width, b.height - part.od / 2 - 0.5, b.yaw_deg, col,
                f"{b.id} {b.datum} {'clamp ' if b.clamp else ''}{b.sensor}".strip())
        fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, scene=dict(aspectmode="data"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Orange blocks carry datums (A: 3 vertical supports, B: 2 lateral on the longest straight; C: end "
                   "stop at the tube start). Grooves are cut by a rod of OD + 2 x clearance swept along the true centerline.")
    with c2:
        st.markdown(f"**Checking fixture** · plate {w:.0f} x {h:.0f} x {tt:.0f} mm · {len(fx.blocks)} blocks · groove "
                    f"clearance {fx.clearance} mm (go/no-go)")
        st.dataframe(pd.DataFrame(fx.block_table()), hide_index=True, width="stretch", height=300)
        if fx.rejected:
            st.caption("Blocks not placed: " + "; ".join(fx.rejected))
        fdir = ART / "parts" / part.part_no / "fixture"
        if (fdir / f"{part.part_no}_fixture.step").exists():
            st.download_button(f"{t('download')} fixture STEP (assembly)", (fdir / f"{part.part_no}_fixture.step").read_bytes(),
                               f"{part.part_no}_fixture.step")
            pb = sorted((fdir / "print_blocks").glob("*.stl"))
            if pb:
                import zipfile

                zb = io.BytesIO()
                with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
                    for p_ in pb:
                        z.write(p_, p_.name)
                st.download_button(f"{t('download')} 3D-printable blocks (.zip of STL)", zb.getvalue(),
                                   f"{part.part_no}_fixture_blocks.zip")
    st.markdown("**Automated checking station: PLC-style sequence** (poka-yoke interlocks)")
    dot = ["digraph{rankdir=LR;bgcolor=transparent;node[shape=box,style=\"rounded,filled\",fillcolor=\"#F4F2EE\",fontname=Helvetica,fontsize=10];"
           "edge[fontname=Helvetica,fontsize=8,color=\"#5B6068\"];PASS[fillcolor=\"#D9F2DF\"];FAIL[fillcolor=\"#F8D9CF\"];"
           "ESTOP[fillcolor=\"#F8D9CF\"];"]
    for a_, b_, cond in TRANSITIONS:
        dot.append(f'{a_.value}->{b_.value}[label="{cond}"];')
    dot.append("}")
    st.graphviz_chart("".join(dot), width="stretch")
    n = sum(b.clamp for b in fx.blocks)
    if "station" not in st.session_state or st.session_state.get("station_part") != part.part_no:
        st.session_state.station = Station(part.part_no, n)
        st.session_state.station_part = part.part_no
    stn: Station = st.session_state.station
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("Simulate inputs, then run a PLC scan:")
        seat = [st.checkbox(f"PX{k + 1} seated", value=True, key=f"seat{k}") for k in range(n)]
        end = [st.checkbox(f"END{k + 1} at stop", value=True, key=f"end{k}") for k in range(2)]
        clamp = [st.checkbox(f"CLAMP{k + 1} closed", value=stn.state.value in ("CLAMPING", "CHECK", "PASS"), key=f"cl{k}")
                 for k in range(n)]
        bc = st.text_input("Barcode scanned this cycle", value=part.part_no)
        x1, x2, x3 = st.columns(3)
        ng = x1.checkbox("NG bin sensor")
        es = x2.checkbox("E-stop")
        lbl = x3.checkbox("Label printed")
        b1, b2, b3 = st.columns(3)
        if b1.button("Scan x1"):
            stn.scan(Inputs(seat=seat, end=end, clamp_closed=clamp, barcode=bc or None, ng_bin=ng, estop=es,
                            label_done=lbl))
        if b2.button("Scan x5"):
            for _ in range(5):
                stn.scan(Inputs(seat=seat, end=end, clamp_closed=clamp, barcode=None, ng_bin=ng, estop=es, label_done=lbl))
        if b3.button("Reset station"):
            st.session_state.station = Station(part.part_no, n)
            stn = st.session_state.station
    with c2:
        o = stn.outputs(Inputs(seat=seat, end=end, clamp_closed=clamp))
        lamp = "🟢" if o.lamp_green else "🔴" if o.lamp_red else "🟠" if o.lamp_amber else "⚪"
        st.markdown(f"### {lamp} {stn.state.value}")
        st.write({"clamp valve": o.clamp_close, "print label": o.print_label, "buzzer": o.buzzer,
                  "passed": stn.passed, "failed": stn.failed, "reason": stn.reason or "-"})
        if stn.history:
            st.dataframe(pd.DataFrame(stn.history[-8:], columns=["from", "to", "because"]).astype(str), hide_index=True)
    st.dataframe(pd.DataFrame(A.io), hide_index=True, width="stretch")
    st.caption("I/O addresses are illustrative (Siemens-style notation).")

# ------------------------------------------------------------------ 5. Line and kaizen
with tabs[4]:
    st.info("The line model is a **synthetic** SimPy simulation (illustrative cycle times, failures and yields), "
            "except the bending yield in the springback scenario, which comes from the real TubeBEND runs.")
    cl = read_json("springback/closed_loop.json")
    c1, c2, c3, c4 = st.columns(4)
    do_reb = c1.toggle("Line rebalancing", value=False)
    do_smed = c2.toggle("SMED on bender", value=False)
    buf_n = c3.slider("Buffer before bender", 1, 20, 2)
    do_cl = c4.toggle("Closed-loop springback", value=False, disabled=cl is None)
    c5, c6 = st.columns(2)
    demand = c5.slider("Demand (parts/day)", 800, 2000, 1500, 50)
    reps = c6.slider("Replications", 2, 10, 4)
    line = baseline_line()
    line = replace(line, demand_per_day=demand)
    if cl:
        line = line.with_station("BEND", latent_fpy=cl["fpy"][cl["baseline_policy"]])
    if do_reb:
        line = kaizen.rebalance(line)
    if do_smed:
        line = kaizen.smed(line)
    line = kaizen.set_buffer(line, buf_n)
    if do_cl and cl:
        line = line.with_station("BEND", latent_fpy=cl["fpy"]["ml"])
    with st.spinner("Simulating..."):
        res = replicate(line, reps=reps, days=3.0)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(t("takt"), f"{line.takt_s:.1f} s")
    k2.metric("Good parts/day", f"{res['per_day'].mean:.0f}", f"± {res['per_day'].ci95:.0f} (95% CI)", delta_color="off")
    k3.metric("Demand met", f"{100 * res['per_day'].mean / demand:.1f}%")
    k4.metric("Scrap", f"{res['scrap_pct'].mean:.2f}%")
    k5.metric("Bottleneck", res["bottleneck"])
    c1, c2 = st.columns(2)
    with c1:
        yz = pd.DataFrame(yamazumi(line))
        fig = go.Figure()
        colors = {"manual": ORANGE, "machine": "#3F5466", "walk": STEEL}
        for kind in ("machine", "manual", "walk"):
            d = yz[yz.kind == kind]
            fig.add_trace(go.Bar(x=d["station"], y=d["seconds"], name=kind, marker_color=colors[kind],
                                 hovertext=d["element"], hoverinfo="text+y"))
        fig.add_hline(y=line.takt_s, line_dash="dash", line_color=INK, annotation_text=f"takt {line.takt_s:.1f} s")
        fig.update_layout(barmode="stack", height=380, title=t("yamazumi"), yaxis_title="seconds",
                          margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")
    with c2:
        oee = pd.DataFrame({k: {"OEE": v.mean} for k, v in res["oee"].items()}).T.reset_index(names="station")
        fig = go.Figure(go.Bar(x=oee["station"], y=100 * oee["OEE"], marker_color=STEEL))
        fig.update_layout(height=380, title=f"{t('oee')} per station (A x P x Q), %", margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")
    kz = read_json("line/kaizen_results.json")
    if kz:
        st.markdown(f"**Kaizen chain (recorded run, {kz['reps']} replications x {kz['days']:g} days, common random "
                    f"numbers):** throughput {kz['throughput_gain_pct']:+.1f}%, scrap {kz['scrap_change_pts']:+.2f} points")
        st.dataframe(pd.DataFrame(kz["rows"]).drop(columns=["note"]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(kz["smed"]), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 6. Process sheet
with tabs[5]:
    st.markdown("**工程表 / process control plan**: operations, machines, control items, inspection, frequency and "
                "reaction plan, filled from the computed program, DFM, fixture and station.")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        xp = write_excel(A, Path(td) / "ps.xlsx")
        pp = write_pdf(A, Path(td) / "ps.pdf")
        c1, c2 = st.columns(2)
        c1.download_button(f"{t('download')} 工程表 (.xlsx)", xp.read_bytes(), f"{part.part_no}_process_sheet.xlsx")
        c2.download_button(f"{t('download')} 工程表 (.pdf)", pp.read_bytes(), f"{part.part_no}_process_sheet.pdf")
    from pipeforge.process_sheet import HEADERS, operations

    st.dataframe(pd.DataFrame(operations(A), columns=[f"{ja} / {en}" for en, ja in HEADERS]), hide_index=True,
                 width="stretch")
    st.markdown("**Engineering summary**")
    s = llm_assist.summarize(A.summary())
    st.write(s["text"])
    st.caption(f"Source: {s['source']}. " + ("An LLM rewrites the computed facts if a key is configured; any number "
               "not in the computed data rejects its text." if s["source"] == "template" else "Checked: every number "
               "appears in the computed data.") + (f" ({s['rejected']})" if s["rejected"] else ""))
    with st.expander("Computed facts given to the assistant (JSON)"):
        st.json(A.summary())

st.divider()
st.caption("PipeForge: a self-directed engineering study (not industrial deployment). TubeBEND: Oz, Knoche, Yazdani, "
           "Engel, Van Laerhoven (2025), Zenodo 10.5281/zenodo.18458823, CC BY 4.0. 日本語の表示は学習中に作成したものです。")
