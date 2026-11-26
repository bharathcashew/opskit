# Contributing

Thanks for helping. The bar for a new check is simple: it is read-only, it is tested, and its findings tell someone what to do next.

## Setup

```bash
git clone https://github.com/bharathcashew/opskit.git && cd opskit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Tests use [moto](https://github.com/getmoto/moto), so no AWS account is needed.

## Adding a built-in check

1. Put it in the right module under `src/opskit/checks/<provider>/`. Modules there are imported automatically.
2. Use an id of the form `<provider>.<service>.<what>`, e.g. `aws.rds.public_snapshots`.
3. Tag it with at least the provider and one of `health`, `security`, `cost`, `governance`.
4. Keep it read-only. Add any new IAM actions to `docs/iam-policy.json`.
5. Make tunable values keyword arguments with defaults, not constants.
6. Add a test in `tests/` that creates a passing and a failing case.

## Status guidelines

- `critical`: something is broken or exposed right now
- `warn`: wasteful, drifting, or will become a problem
- `error`: reserved for the runner when a check raises; don't return it yourself

## Pull requests

Keep PRs focused, describe what the check catches and why, and include sample output.
