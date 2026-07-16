# Methods

## Evaluation target

RecommendSignal evaluates whether a policy can rank items that appear in later observed implicit-feedback events. This is a historical replay target. It is not complete preference measurement, counterfactual policy value, or a treatment effect.

## Global temporal folds

Distinct event timestamps are sorted on one global timeline. An initial fraction establishes the first training cutoff. The remaining timeline is divided into nonoverlapping test windows. Fold (f) trains on every eligible event with timestamp earlier than its cutoff and tests on events from that cutoff until the next boundary.

This global construction prevents an earlier prediction from learning another user’s later event. Per-user leave-last-out splits can violate that constraint in collaborative models when future interactions from other users enter training.

Only catalog items with `available_at` no later than the fold cutoff are candidates. Features are assumed to be the historically valid snapshot available at that cutoff. The evaluator reports test events excluded because their items were not yet eligible.

## Candidate protocol

Every eligible catalog item not previously interacted with by the user is scored. No sampled negatives are used. This makes metrics comparable across the four policies under the declared catalog, although historical logs still contain exposure and selection bias.

## Policy definitions

### Popularity

The popularity score is `log(1 + weighted pre-cutoff interaction frequency)`. It is a nonpersonalized benchmark and a diagnostic for popularity dominance.

### Content-based

Item feature rows are L2-normalized. A user profile is the event-weighted sum of normalized features for their pre-cutoff items. Candidate scores are cosine similarities to that profile. If all candidate content scores tie, the policy declares and reports a popularity fallback.

### Collaborative

The app constructs a weighted implicit user-item matrix from training data. Item-item similarities are cosine similarities between item interaction columns, with the diagonal set to zero. A candidate’s score is the similarity-weighted sum over a user’s history. An all-tie candidate set triggers a declared popularity fallback.

### Hybrid

Popularity, content, and collaborative scores are converted to within-user full-catalog relative ranks. The declared weights should be recorded before the test outcomes are examined. Presets make choices explicit but cannot prevent repeated post-hoc tuning; once a holdout informs the mix, it is no longer an untouched final holdout.

## Metrics

For user (u), relevant test set (R_u), and top-K slate (L_{u,K}):

The relevant test set (R_u) contains the user's test-window items minus their pre-cutoff items: repeat interactions are excluded from relevance because repeats are excluded from candidates, so every relevant item is one the policies were allowed to recommend. A user whose test window contains only repeats is not evaluated in that fold.

- `Recall@K = |R_u ∩ L_u,K| / |R_u|`.
- `NDCG@K` sums binary relevance discounted by `1/log2(rank+1)` and divides by the ideal DCG for `min(K, |R_u|)` hits.
- `Coverage` is distinct recommended items divided by eligible catalog items, calculated per fold and then averaged.
- `Novelty` is mean `-log2(p_i)`, where `p_i` is the item’s add-half-smoothed pre-cutoff event frequency.
- `Exposure HHI` is the sum of squared recommendation-exposure shares within a fold.
- `Top-10 share` is the exposure share received by the ten most-exposed items, or all exposed items when fewer than ten exist.

Cold users have no more than the declared number of unique training items. A cold user is therefore a low-history user, not a new user: truly zero-history users are never evaluated, because eligibility requires the declared minimum pre-cutoff history. Cold items have no more than the declared number of training events. Cold-item Recall@K uses only relevant test items meeting that definition and remains missing when a user has none.

## Aggregation and uncertainty

Recall and NDCG are averaged within user across available folds, then across users so each user receives equal macro weight. Their 95% intervals use a percentile bootstrap over user-level means. One footnote on the remaining summary columns: cold-user recall and the fallback rate are simple means over user-fold rows, so a user evaluated in several folds carries more weight there than in the headline user-macro Recall and NDCG.

Policy contrasts first pair candidate and reference metrics within user and fold, then average fold differences within user. The app reports a paired user-level t interval and two-sided test. Benjamini–Hochberg q-values adjust the displayed family of policy-metric comparisons. “Clear offline increase” requires an interval above zero and q ≤ .05; it remains strictly an offline label.

Subgroup tables average user-level values inside the supplied stable subgroup. Max-minus-min gaps are descriptive and receive no automatic fairness interpretation.

## Known limitations

- Observed events are affected by historical exposure, interface, inventory, and selection policies.
- A missing interaction is neither a known negative nor proof of irrelevance.
- New but relevant items can be impossible to judge from historical behavior.
- User resampling does not solve dependence among users, items, sessions, or network effects.
- Binary relevance ignores event strength in test metrics, even though event weights inform training.
- Baseline algorithms omit context, sequence, diversity reranking, constraints, inventory, latency, and production serving concerns.
- Offline metrics do not estimate commercial lift, satisfaction, retention, welfare, or causality.
