# Changelog

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
