# json_sample_generator

Generate sample data from JSON Schema or OpenAPI (OAS) schemas. Create realistic samples for tests, examples, and fixtures.

[![CI](https://github.com/bartoszm/sample_generator/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bartoszm/sample_generator/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/sample-generator.svg)](https://pypi.org/project/sample-generator/)
[![PyPI downloads/month](https://img.shields.io/pypi/dm/sample-generator.svg)](https://pypi.org/project/sample-generator/)
[![License](https://img.shields.io/github/license/bartoszm/sample_generator.svg)](https://github.com/bartoszm/sample_generator/blob/main/LICENSE)
[![Python versions](https://img.shields.io/pypi/pyversions/sample-generator.svg)](https://pypi.org/project/sample-generator/)

## Installation

From PyPI:

```bash
pip install sample-generator
# importable module name remains `json_sample_generator`
```

Or with uv:

```bash
uv add sample-generator
```

## Quickstart

Prerequisites:
- Python 3.12+
- uv installed

Install uv (Linux/macOS):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Set up the project:
```bash
# Clone the repo
git clone https://github.com/<your-username>/json_sample_generator.git
cd json_sample_generator

# (Optional) create a virtualenv managed by uv
uv venv  # creates .venv/

# Install runtime deps
uv sync

# For development (tests, tools, etc.)
uv sync --group dev
```

Run tests:
```bash
uv run pytest -q
```

Run examples:
```bash
uv run python examples/simple_value_example.py
```

## Developer guide

Code quality tools used by the project

- uv (astral.sh/uv) — virtualenv + task runner used in CI
- ruff — linting (CI runs `uvx ruff check .`)
- black — formatting (CI runs `uvx black --check .`)
- isort — import sorting (CI runs `uvx isort --check-only .`)
- pytest — test runner (CI runs `uv run pytest -q`)

Automated-fix hints

- Run ruff's auto-fixer to apply quick lint fixes:
	```uvx ruff check . --fix```
- Reformat code with black:
	```uvx black .```
- Sort imports with isort:
	```uvx isort .```
- Run the full CI steps locally (create venv first):
	```bash
    uv venv
	uv sync --group dev
	uvx ruff check .
	uvx black --check . && uvx isort --check-only .
	uv run pytest -q
    ```

These commands mirror what GitHub Actions runs so you can reproduce and fix CI failures locally.

Build and publish reminders

The repository's publish workflow builds with `uv build` and uses the pypa/gh-action-pypi-publish action; for first-time releases you may need a PyPI API token (or configure OIDC/trusted publishing on PyPI).

Pre-commit (recommended):
```bash
uvx pre-commit install
uvx pre-commit run --all-files
```

## User guide: Scenarios

Scenarios let you override generated values per field path with simple values or callables, and optionally with pattern-based rules. They accept a Context so overrides can depend on other fields.

See the full guide (including `default_data`) in [`docs/SCENARIOS.md`](docs/SCENARIOS.md).

## Contributing

See `CONTRIBUTING.md`.

## License

MIT. See `LICENSE`.