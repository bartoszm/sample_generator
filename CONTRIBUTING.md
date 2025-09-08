# Contributing

Thanks for your interest in contributing! Please follow these quick steps:

## Development setup
- Use Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Create a venv and install deps:
  - `uv venv && uv sync --all-extras --group dev`
- Run tests: `uv run pytest -q`

## Code quality
- Format with `black` and `isort`
- Lint with `ruff`
- Type-check with `mypy`
- Pre-commit hooks: `uvx pre-commit install`

## Pull requests
- Create a feature branch from `main`
- Add tests for new behavior
- Update docs/README if needed
- Ensure CI is green

## Releasing
- Maintainers: bump version in `src/json_sample_generator/__init__.py`
- Tag and GitHub Actions will build and publish to PyPI when a release is created
