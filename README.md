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

Key `Scenario` flags:

- `minimal_mode=True` — emit only `required` fields plus any explicitly referenced by the scenario.
- `scenario_only=True` — stricter: emit **only** fields covered by the scenario (overrides, pattern_overrides, default_data, oneof_selectors), regardless of `required`. Produces focused fixtures that may be schema-invalid by design.

See the full guide (including `default_data`) in [`docs/SCENARIOS.md`](docs/SCENARIOS.md).

## User guide: Loading from OpenAPI (OAS)

To load a component schema from an OpenAPI Specification:

```python
import yaml
from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema

with open("api.yaml") as f:
    oas = yaml.safe_load(f)

schema = Schema.from_oas(oas, name="Pet")
gen = JSONSchemaGenerator(schema)
sample = gen.generate()
```

This correctly resolves cross-component `$ref` pointers. See the full guide in [`docs/OPENAPI.md`](docs/OPENAPI.md) for advanced usage, the `jsonref` caching details, and when to use `from_raw_data` vs `from_oas`.

## User guide: Scalar constraints

When no scenario override applies, `DefaultValueGenerator` draws a value
that honours the keywords below. When a schema cannot be satisfied it
raises `ValueError` naming the schema, rather than returning a value that
would fail validation.

- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` — both the
  numeric form and the draft-4 / OpenAPI 3.0 boolean form are understood;
  when a plain and an exclusive bound are both given, the tighter one
  wins. With a single bound the default span is kept: `{"minimum": 576}`
  draws 576..676, `{"maximum": -5}` draws -105..-5 (integers), and numbers
  use a span of 1.0. Exclusive bounds are exact (`floor(x) + 1`,
  `ceil(x) - 1` for integers, the open interval for numbers). An empty or
  inverted range raises.
- `multipleOf` — a random multiple inside the bounds. A one-sided bound is
  widened to reach the first multiple (`minimum: 99, multipleOf: 7` can
  give 105). Float steps are checked the way validators do, so
  `0 < x < 0.4, multipleOf: 0.1` raises when the only candidate, `0.3`,
  fails `0.3 / 0.1` in floating point.
- `minLength`, `maxLength` — applied on their own and together with
  `pattern` or `format`. `email`, `hostname`, `uri`, `url` and `phone` are
  drawn from Faker first and then built to a fitting length (`a@xmi.vw`
  for `maxLength: 12`). Fixed-shape formats (`uuid`, `ipv4`, `ipv6`,
  `date`, `time`, `date-time`) must fit as they are, so `uuid` with
  `maxLength: 10` raises. A `pattern` is drawn with its open-ended repeats
  capped at `maxLength` and, as a second try, floored at `minLength`, so
  `^[a-z]{200,}$` and `^[a-z]+$` with `minLength: 150` both work.
  `minLength > maxLength` raises. Unknown formats are annotations and take
  the plain string path.
- `format` — `date-time` and `time` values carry a UTC offset
  (`2025-09-28T21:09:04.826286+00:00`, `19:47:52Z`), as RFC 3339 requires.

## User guide: Break Scenarios

Break scenarios take a valid generated sample and intentionally corrupt it so that it fails JSON Schema validation — useful for negative-path tests, validator error-message testing, and schema-evolution checks.

See the full guide in [`docs/BREAK_SCENARIOS.md`](docs/BREAK_SCENARIOS.md).

## User guide: Capping array size with `generator_max_items`

When a schema declares a large `maxItems` (e.g. `10000`) the generator will, by default, pick a random length up to that bound and produce that many child elements. For deeply nested schemas this can be very slow and produce huge payloads that are not useful for tests or fixtures.

Pass `generator_max_items` to the `JSONSchemaGenerator` constructor to apply a *generator-wide* upper bound on array length. It does **not** replace the schema's `maxItems`; it only caps it from above.

```python
from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.models import Schema

schema = Schema(data={
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "maxItems": 10000,           # schema permits very large arrays
            "items": {"type": "string"},
        }
    },
    "required": ["tags"],
})

# Cap every array generated by this instance at 5 elements.
gen = JSONSchemaGenerator(schema, generator_max_items=5)
sample = gen.generate()
assert len(sample["tags"]) <= 5
```

### Algorithm

For each array node, the effective upper bound is computed as:

1. If the schema **does not** declare `maxItems`:
   - use `generator_max_items` when it is set,
   - otherwise fall back to `max(minItems, 2)` (the legacy default).
2. If the schema **does** declare `maxItems`:
   - use `min(maxItems, generator_max_items)` when the cap is set,
   - otherwise use `maxItems` as-is.
3. The final element count is `random.randint(minItems, max_items)`.

Consequences:

- `generator_max_items=None` (the default) preserves existing behavior — no global cap is applied.
- When a schema omits `maxItems`, setting `generator_max_items=N` lets arrays grow up to `N` (instead of being silently capped at the `2` default).
- The schema's `minItems` is always respected. If a schema demands `minItems: 10` but you set `generator_max_items=5`, `random.randint(10, 5)` will raise `ValueError`. Choose a cap that is not lower than any `minItems` you expect to encounter.
- The schema's `maxItems` still wins when it is *smaller* than the global cap (`min(...)` semantics).
- Applies to every array node in the schema for that generator instance — there is no per-path override. Use `scenario.overrides` if you need to control a specific array's contents.

### When to use it

- Generating fixtures from third-party OpenAPI specs that declare unrealistically large `maxItems`.
- Speeding up property-based tests where the array size is incidental.
- Producing compact sample payloads for documentation or examples.

## Contributing

See `CONTRIBUTING.md`.

## License

MIT. See `LICENSE`.