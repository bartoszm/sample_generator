# json_sample_generator

Generate sample data from JSON Schema or OpenAPI (OAS) schemas. Create realistic samples for tests, examples, and fixtures.

Badges (optional):

- CI: GitHub Actions status
- PyPI: version, downloads
- License: MIT

## Installation

From PyPI:

```bash
pip install json_sample_generator
```

Or with uv:

```bash
uv add json_sample_generator
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

Code style:
- PEP 8; line length 79
- Type hints everywhere

Common tasks:
```bash
# Lint
uvx ruff check .

# Format
uvx black .
uvx isort .

# Type-check
uvx mypy .

# Test
uv run pytest -q
```

Build and publish:
```bash
# Build sdist + wheel
uv build

# Dry-run publish (uses ~/.pypirc or env vars)
uv publish --dry-run
```

Release to PyPI:

- Bump `__version__` in `src/json_sample_generator/__init__.py`
- Create a GitHub release (tag must match version)
- The publish workflow will build and upload to PyPI via trusted publishing

Pre-commit (recommended):
```bash
uvx pre-commit install
uvx pre-commit run --all-files
```

## User guide: Scenarios

Scenarios let you override generated values per field path with simple values or callables, and optionally with pattern-based rules. They accept a Context so overrides can depend on other fields.

See the full guide (including `default_data`) in `docs/SCENARIOS.md`.

## Contributing

See `CONTRIBUTING.md`.

## License

MIT. See `LICENSE`.