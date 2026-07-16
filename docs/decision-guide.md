# Decision guide

## Start with the protocol, not the winner

Confirm that each fold respects the global timeline, that item availability is credible, that the full candidate catalog matches the intended product surface, and that feature values existed at prediction time. A polished leaderboard cannot rescue a leaked protocol.

## Read ranking and distribution together

A higher Recall@K or NDCG@K can coincide with narrower coverage and heavier exposure concentration. That may be acceptable, harmful, or strategically irrelevant depending on the product objective, supplier ecosystem, inventory, and user experience. RecommendSignal keeps these quantities separate so the decision owner must state the trade-off.

## Inspect temporal stability

A policy that leads on average but reverses across folds may be sensitive to seasonality, catalog churn, cohort mix, or model aging. Investigate those changes before escalating the policy.

## Treat cold start as its own problem

Content-based policies can score interaction-cold items when valid features exist. Collaborative methods generally need behavioral history. Compare both cold-user and cold-item results; they answer different questions.

## Investigate subgroup gaps

Check sample size, history length, catalog eligibility, exposure, and relevance measurement inside each group. A gap can arise from data coverage or policy design and does not identify its cause. Fairness assessment requires domain-specific harms, rights, and stakeholder judgment beyond this dashboard.

## Handoff to ExperimentSignal

Use the offline evaluation to narrow candidates and document guardrails. Then preregister an online randomized test that defines:

- the policy assignment unit and interference risk;
- primary commercial or user-value outcome;
- exposure and compliance measurement;
- guardrails for concentration, complaints, latency, and vulnerable groups;
- sample size, duration, stopping rule, and multiple testing;
- rollback and monitoring criteria.

Only that experimental workflow can support an incremental lift claim under its assumptions.
