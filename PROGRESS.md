# PipeForge progress log

Resume point for any new session: read this file, then the brief
(`C:\Users\goura\Downloads\PROMPT_YAMATO_PIPEFORGE.md`), then continue from
the first phase that is not marked done. Research notes live in
`C:\Users\goura\Downloads\pipeforge-research\`.

Deadline: Thursday 26 Nov 2026, 10:00 IST (repo, deployed app, demo video, CV bullet).

## Environment (checked 25 Nov 2026, 06:07 IST)

- Windows 11; system Python 3.14.6 is too new for CadQuery wheels, so the
  project uses `uv venv --python 3.12` (3.12.13).
- `cadquery 2.8.0`, `xgboost 3.4.1`, `shap 0.54.1`, `streamlit 1.67.0`,
  `simpy`, `openpyxl`, `reportlab`, `shapely`, `trimesh` all install and import.
- `make` is not installed on this machine; the Makefile targets are for CI and
  Linux/macOS. On Windows run the commands inside each target directly.

## Phases

| Phase | Work | Budget | Status | Time used |
|---|---|---|---|---|
| 1 | Env check, scaffold, materials with sources | 0.75 h | scaffold done; materials waiting on sourced values | 0.3 h |
| 2 | M1 geometry, CAD, drawing, tests | 3 h | done (43 tests) | 1.0 h |
| 3 | M2 DFM, mechanics, compensation, ENGINEERING_NOTES | 2 h | todo | |
| 4 | M3 TubeBEND springback ML, model card, closed loop | 4 h | todo | |
| 5 | M4 fixture, M4b station | 4 h | todo | |
| 6 | M6 line sim, kaizen, A3, transfer playbook | 3 h | todo | |
| 7 | M7 process sheet (+ LLM assistant if a key is given) | 1.5 h | todo | |
| 8 | Streamlit app, 3D showcase site, deploy, CI, README, README_ja | 2.5 h | todo | |
| 9 | CV outputs, STUDY_GUIDE, 30 Q&A | 0.5 h | todo | |

## Log

- 06:07 Environment checked. CadQuery needs Python 3.12; uv venv created.
- 06:20 Research agents launched: TubeBEND facts and licence; engineering
  sources (JIS values, bend die chart, formulas); award-level design and ATS keywords.
- 06:55 M1 done: `geometry.py` (XYZ to and from LRA, tangent points, developed
  length), `mesh.py` (dependency-free closed tube mesh, binary STL), `cad.py`
  (CadQuery B-rep, STEP/STL; volume equals annulus area times developed length
  to 1e-15), `drawing.py` (A3 third-angle sheet with silhouettes, bend table,
  title block). Five synthetic sample parts.

## Decisions

- XYZ round trip is exact because LRA keeps a `Placement`; a bare LRA (what a
  bender carries) is compared by rigid alignment instead.
- Drawing silhouettes come from projecting the mesh and merging triangles,
  so they are correct for bends seen edge-on.
- The hosted app will not need CadQuery: `mesh.py` gives 3D and STL for any
  input part; STEP files for samples are pre-generated in `artifacts/`.
