# Data guide

## Interactions

One row is one observed positive event.

| Column | Required | Meaning |
|---|---:|---|
| `user_id` | yes | Stable user identifier. |
| `item_id` | yes | Identifier found in the item catalog. |
| `timestamp` | yes | Event time used by the global temporal split. |
| `event_weight` | no | Positive training strength; defaults to 1. |
| `subgroup` | no | One stable declared label per user; defaults to `All users`. |
| `event_type` | no | Descriptive provenance retained in source data. |

Exact user-item-timestamp duplicates are rejected because they commonly indicate ingestion duplication. Repeat interactions at different times are allowed. Timestamps are normalized to UTC.

## Item catalog

| Column | Required | Meaning |
|---|---:|---|
| `item_id` | yes | Unique catalog identifier. |
| `item_name` | yes | Human-readable label. |
| `available_at` | recommended | Earliest time the item could be recommended. |
| `feature_*` | at least one | Finite numeric content feature known at prediction time. |

If `available_at` is omitted, RecommendSignal assumes the full catalog predates the log and displays a warning. This assumption can hide availability leakage.

Feature columns may be one-hot topics, continuous embeddings reduced to interpretable components, or other numeric descriptors. They must be created without using information from after the evaluated cutoff. Do not include later performance, later reviews, or later interaction aggregates as content features for an earlier fold.

## Subgroups

Use groups that are analytically and legally appropriate for the domain. The app requires one stable label per user because time-varying labels need a different estimand and data model. Small groups can produce unstable results. A difference is not automatically unfair; a small difference is not automatically safe.

## Event weights

Weights affect model fitting, not the binary test relevance definition. Document the rule before evaluation—for example `open=1`, `save=2`, `complete=3`. Do not choose weights after inspecting the leaderboard.

## Privacy and minimization

User identifiers should be pseudonymous. Remove direct identifiers, free text, and attributes not needed for the evaluation. Recommendation slates and inferred profiles can expose sensitive preferences even when names are absent.

## Templates

The app and `examples/` directory provide separate CSV templates plus a combined XLSX workbook. Uploaded workbooks may use `interactions` and `items` sheet names; when absent, the first sheet is read.
