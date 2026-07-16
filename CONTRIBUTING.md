# Contributing

Contributions should preserve the global-timeline protocol, full-catalog candidate evaluation, explicit metric definitions, privacy boundary, and the separation between offline evidence and causal lift.

Before submitting a change:

1. Add or update deterministic tests.
2. Run `python -m pytest` and `python -m ruff check .`.
3. Update documentation and fictional examples when the data contract changes.
4. Do not introduce proprietary course content, private interaction logs, or third-party data without appropriate rights.
5. Do not add a universal recommendation score or causal language to offline results.
