# Changelog

## 1.1.0 — 2026-10-02

Signal brand refresh and Signal Hub entry point. The evaluation protocol, policies, metrics, data contract and exports are unchanged.

### Brand

- Display name written **Recommend Signal** (with a space) in the app, README, docs, AI protocol, launchers and metadata. Package, file and environment-variable names stay `recommendsignal` / `RECOMMENDSIGNAL_*`. The name screen still covers the exact string “RecommendSignal”; no new clearance is claimed.
- The app uses the shared `signal_theme` module (Organic Signal design, Customer family colour `#aa5d83`, Figtree): sidebar lockup, masthead, hero, cards, notes, footer, Plotly template and the mark as favicon replace the pasted styles and the `suite_brand` module.
- Charts use the per-app Plotly template and the family colorway instead of the old teal, slate, amber and violet series colours; chart meaning is unchanged.
- New banner, social preview and marks in `assets/`; the old banner SVG is removed. `.streamlit/config.toml` uses the family colours.
- README follows the Signal template; bug-report and feature-request issue templates added.

### Signal Hub contract

- `recommendsignal.ui` exposes `APP_INFO` and `render()`, so Signal Hub can embed the app; `app.py` is now a thin standalone entry point.
- All session-state and widget keys are namespaced `recommend:` (including the page selector, data-source controls and evaluation sliders). The loaded interaction log and catalog live in session state.
- Page errors are caught and shown in the app; unexpected technical details appear only with `RECOMMENDSIGNAL_DEBUG=1`.
- `streamlit` and `plotly` moved to a `ui` extra (also in `test`); the analysis core installs without them. `requirements.txt` and the Docker image install the `ui` extra.
- New tests: no Streamlit/Plotly import outside `recommendsignal.ui`, the core imports without them, `render()` runs from a script without a page config, every widget key is namespaced, and every page renders from the packaged files alone (as Signal Hub installs them), with no repo-root files.

## 1.0.1 — 2026-07-16

### Security

- Export sanitizer now also neutralizes formula-like column headers and strips control characters; Docker images keep application code root-owned; defusedxml hardens workbook XML parsing. Uploads gain size, expansion, row, and column caps (50 MB / 200 MB expanded / 500k rows / 200 columns), and every Excel/CSV export is formula-neutralized.

## 1.0.0 — 2026-07-16

- Added global-timeline expanding-window evaluation.
- Added popularity, content-based, item-item collaborative, and preweighted hybrid baselines.
- Added Recall@K, NDCG@K, coverage, novelty, exposure concentration, cold-start, subgroup, and stability reporting.
- Added paired user-level policy contrasts and uncertainty.
- Added deterministic fictional examples, local templates, and auditable XLSX export.
- Added explicit ExperimentSignal handoff and offline/causal boundaries.
- Recorded the basic RecommendSignal working-name screen.
