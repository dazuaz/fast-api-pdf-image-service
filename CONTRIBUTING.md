# Contributing

Contributions are welcome. Please open an issue first for large changes so we can agree on direction.

## Setup

- Python **3.12** (see `requires-python` in `pyproject.toml`).
- [uv](https://docs.astral.sh/uv/) recommended:

```bash
uv sync
```

## Run locally

```bash
uv run uvicorn app.main:app --reload --port 5001
```

## Tests

```bash
uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

CI runs the same command with a frozen lockfile (`uv sync --frozen`).

## Pull requests

- Keep changes focused on one concern when possible.
- Add or update tests for behavior changes.
- Ensure tests pass locally before submitting.

## Code style

Match existing patterns in the codebase (imports, typing, and structure). No strict formatter is enforced in CI yet; consistency matters more than tooling debates.
