# Architecture

One part definition (XYZ points, OD, wall, CLR, material) flows through every module. `pipeline.analyze()` is the single entry point that the app, the artifacts script, the process sheet and the LLM assistant share. No module hard-codes a result: the README, the app and the site all read files that scripts regenerate.

```mermaid
flowchart LR
    P["Part<br/>XYZ, OD, t, CLR, JIS material<br/>(parts.py, materials.py)"]
    G["geometry.py<br/>XYZ to LRA, tangent points,<br/>developed length"]
    C["cad.py (CadQuery)<br/>exact B-rep, STEP/STL"]
    M["mesh.py<br/>closed mesh, STL, 3D view<br/>(no CAD kernel)"]
    D["drawing.py<br/>A3 third-angle sheet,<br/>bend table, title block"]
    F["dfm.py<br/>chart, clamp, ends,<br/>collision, elongation"]
    K["mechanics.py<br/>springback, thinning,<br/>ovality (estimates)"]
    ML["springback_ml/<br/>TubeBEND loader, virtual CMM,<br/>GroupKFold, XGBoost, SHAP"]
    Y["compensation.py<br/>LRA to YBC: overbend,<br/>radius-growth feed correction"]
    X["fixture.py<br/>blocks, grooves, 3-2-1 datums"]
    S["station.py<br/>PLC-style state machine,<br/>poka-yoke, I/O list"]
    L["line_sim.py (SimPy)<br/>takt, OEE, Yamazumi"]
    Z["kaizen.py<br/>rebalancing, SMED, buffer,<br/>closed loop"]
    PS["process_sheet.py<br/>工程表 XLSX / PDF"]
    LLM["llm_assist.py<br/>grounded summary,<br/>number check"]
    PL(("pipeline.analyze"))
    APP["app/streamlit_app.py"]
    SITE["site/ (three.js, GSAP)<br/>reads site/data.json"]

    P --> G --> C & M & D & F
    K --> F
    K --> Y
    ML --> Y
    G --> Y
    G --> X --> S
    ML -->|"bend yield on real runs"| Z
    L --> Z
    F & Y & X & S --> PL
    PL --> PS & LLM & APP
    Z --> APP
    ML --> APP
    PL --> SITE
    Z --> SITE
```

## Data and regeneration

| Output | Made by | Consumed by |
|---|---|---|
| `data/tubebend/derived/runs.csv` | `python -m pipeforge.springback_ml.features` (needs the 797 MB download) | `train`, CI |
| `artifacts/springback/*` (metrics, models as XGBoost JSON, plots) | `python -m pipeforge.springback_ml.train` | app, kaizen, README |
| `artifacts/line/kaizen_results.*` | `python -m pipeforge.kaizen` | app, A3, README |
| `artifacts/parts/<part>/*` (STEP, STL, drawing, YBC, 工程表, DFM, fixture) | `python scripts/build_artifacts.py` (needs CadQuery) | app downloads on the host |
| `docs/figures/*.png` | `python scripts/build_figures.py` | README |
| `site/data.json` | `python scripts/build_site_data.py` | showcase site |

## Design decisions

1. **Two geometry back-ends.**
   - CadQuery gives exact solids for STEP; its volume equals annulus area × developed length to 1e-15.
   - `mesh.py` sweeps rings with parallel-transport frames, so the hosted app draws and exports STL for any typed-in part without a CAD kernel.
2. **LRA keeps a placement**, so XYZ round trips are exact. A bare LRA (what a bender holds) is compared by rigid alignment.
3. **Grooves are cut by a swept rod.** They follow arcs and slopes exactly; a CAD test shows the go/no-go behaviour.
4. **Safe data loading.** A restricted unpickler loads TubeBEND, and models are saved as JSON, so no pickle runs in the app.
5. **Honest evaluation.** GroupKFold by machine setup, fixed hyperparameters, a physics baseline, and random KFold shown only as the optimistic contrast.
6. **ML gated to its domain.** Outside the TubeBEND tube the pipeline falls back to physics or a measured value and says so.
7. **The LLM cannot add numbers.** Its text is rejected if any number is not in the computed JSON, and a deterministic template is always available.
8. **One transition table** drives the station logic, the Mermaid diagram, the app's graph and the tests.
9. **Common random numbers** across kaizen scenarios, so differences come from the change, not the noise.
