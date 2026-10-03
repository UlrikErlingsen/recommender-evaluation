# Changelog

## 1.2.0 — 2026-10-03

### Larger datasets

- Larger datasets: run locally (standalone, a local Signal Hub or an internal deployment), Recommend Signal no longer sets any limit on file size, rows, columns, users or catalog items; memory is the limit. The former 50 MB upload, 200 MB expanded-workbook, 500,000-row, 200-column and 2,500-item limits, plus a 1,000-repetition bootstrap cap, now apply only in the public demo (`SIGNAL_PUBLIC=1`), where messages say they are demo limits. All caps live in the new `recommendsignal.limits` module.
- Streamlit's upload cap is 10,000 MB: `.streamlit/config.toml`, `RECOMMENDSIGNAL_MAX_UPLOAD_MB` (default 10000, was 200) in both launchers, and `STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000` in the Docker image.
- Running out of memory while loading or evaluating is reported as a plain "not enough memory on this computer" message.
- Users are scored in batches with matrix operations in parallel threads: slates use a linear-time top-K selection, popularity ranks need no per-user sort, and content and collaborative scores use the same per-user products as before, so every slate, metric and interval is identical to 1.1.0 on the same data. The demo evaluates about ten times faster. Large catalogs normalize the item similarity in place; user bootstrap replicates are drawn in blocks when there are very many users.
- The app reads each pair of uploads once and keeps validation and evaluation in the session instead of re-reading, re-hashing and copying the data on every rerun.
- Exports keep the full data: new user-metrics and recommendation-slates CSVs hold every row, a workbook sheet too large for Excel points to its CSV, and large evidence files are built when their button is clicked.
- Measured on a 24-thread desktop: 5 million interactions (400,000 users, 2,000 items) are evaluated over three folds in about 3 minutes, with a peak of about 4.2 GB.

### Suite

- Suite: Rival, Reach, Learn and Blueprint Signal added to the suite table.

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
