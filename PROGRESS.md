# PipeForge progress log

Resume point for any new session: read this file, then the brief
(`C:\Users\goura\Downloads\PROMPT_YAMATO_PIPEFORGE.md`), then continue from
the first item not marked done. Research notes are in
`C:\Users\goura\Downloads\pipeforge-research\`: `tubebend.md`,
`engineering.md` (every value with its URL) and `design-ats.md`.

**Deadline:** Thursday 26 Nov 2026, 10:00 IST. Due by then: the repo, the deployed app, a demo video and the CV bullet.

## Warnings for whoever resumes

- **Never run the fixture CAD export for PF-BL-0476** (4.76 mm brake line). The OpenCascade boolean runs away with memory and has crashed the whole session three times. `scripts/build_artifacts.py` skips fixture CAD below 6 mm OD for this reason.
- **Work in foreground steps and commit after each.** Background shell jobs and subagents die when the session restarts.
- **Ask the user before** creating the GitHub repo, logging in to hosting, or adding any API key.

## Environment (checked 25 Nov 2026, 06:07 IST)

- **Python:** the Windows system Python is 3.14.6. CadQuery has no wheels for it, so the project uses `uv venv --python 3.12` (3.12.13).
- **Install:** `uv pip install -e .` (editable), plus `requirements-dev.txt`.
- **Make:** not installed on this machine. The Makefile is for CI and Linux/macOS; on Windows run the commands inside each target directly.

## Status

| Item | Status |
|---|---|
| Env check, scaffold, materials with sourced values | done |
| M1 geometry, CAD, drawing | done |
| M2 DFM, mechanics, compensation | done |
| M3 TubeBEND springback ML, closed loop | done |
| M4 fixture, M4b station | done |
| M6 line sim, kaizen | done |
| M7 process sheet, grounded LLM assistant | done |
| Streamlit app (AppTest smoke tests) | done |
| Artifacts for 6 parts | done (brake-line fixture CAD skipped, see above) |
| 3D showcase site (`site/`) | partial: index.html, style.css and 3D modules exist; app.js missing; not verified |
| README, README_ja | todo |
| docs: ENGINEERING_NOTES, FIXTURE_DESIGN, KAIZEN_A3, LINE_TRANSFER_PLAYBOOK, ARCHITECTURE, MODEL_CARD | todo |
| figures script, CI workflow | todo |
| GitHub repo + Streamlit deploy (needs the user's OK and logins) | todo |
| CV pack, STUDY_GUIDE, 30 Q&A, demo shot list | todo |

## Key results (all from committed artifacts)

**Springback on TubeBEND.** 315 runs in 67 setup groups, evaluated with GroupKFold by setup (5 folds × 5 repeats).

| Model | MAE | R² |
|---|---|---|
| XGBoost, setup features only | 0.050 ± 0.016° | 0.91 ± 0.08 |
| Mean baseline | 0.245° | |
| Physics estimate | 0.35° predicted vs 2.60° measured | |

**Closed loop at ±0.5° on real runs.**
- No compensation: 0%.
- One constant offset: 88.3%.
- ML on setup features: 99.7%.

**Line (synthetic).** Baseline to all four kaizen: 940 to 1,396 good parts/day (+48.5%), scrap 13.8% to 2.9%.

**DFM** catches the A6063-T5 coolant pipe: 20% elongation needed against 8% minimum.

## Log

- **06:07** Environment checked; research agents launched.
- **06:55** M1 committed.
- **~07:10** M4/M4b committed.
- **~07:40** M2/M3/M6 committed.
- **~10:59** Session restarted. M7 committed.
- **11:10** App committed.
- **11:24** Artifacts committed.
