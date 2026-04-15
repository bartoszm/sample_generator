# User Guide: Scenarios

This library generates sample JSON from JSON Schema/OpenAPI. Scenarios let you override generated values deterministically or dynamically.

## What is a Scenario?
A `Scenario` captures how particular fields should be set during generation.

- Use simple values for fixed fields.
- Use callables for dynamic values that can depend on the current `Context`.
- Optional `pattern_overrides` apply by substring matching on the property path.

Normalization: `Scenario.normalize()` converts any simple values into callables under the hood so the generator can treat all overrides uniformly. It mutates the Scenario instance; call it only once at the end or recreate your scenario if you need raw values again.

## The Context object
Overrides receive a `Context` with helpful info:
- `prop_path`: dotted path of the field (e.g., `address.city` or `phones[0].number`).
- `data`: the partially built result object so far.
- `schema_data`: the schema node for the current property.
- `schema_path`: when the current node comes from a `$ref`, its reference path.

## Basic usage
```python
from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema, Scenario

schema = Schema(data={
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "email": {"type": "string", "format": "email"},
        "age": {"type": "integer"},
        "address": {
            "type": "object",
            "properties": {
                "city": {"type": "string"}
            }
        }
    }
})

# Simple values get normalized to callables automatically
scenario = Scenario(
    name="demo",
    overrides={
        "id": "user-1",
        "age": 30,
        "address.city": "Dublin",
    }
).normalize()

gen = JSONSchemaGenerator(schema)
result = gen.generate(scenario)
```

## Callable overrides

```python
def derived_email(ctx):
    # You can use ctx.data to reference other fields already set
    name = ctx.data.get("name", "user").lower()
    return f"{name}@example.com"

scenario = Scenario(
    name="callables",
    overrides={
        "name": "Alice",
        "email": derived_email,  # receives Context
    }
).normalize()
```

## Pattern overrides
`pattern_overrides` apply a rule when the substring is present in the property path.

```python
scenario = Scenario(
    name="pattern",
    pattern_overrides=[
        ("phones[", lambda ctx: "+100000000"),  # applies to phones[0].number, phones[1]..., etc.
        ("address.", "N/A"),  # sets all address.* fields to "N/A" unless more specific overrides exist
    ],
).normalize()
```

Notes:
- Matching is substring, not regex. Use specific substrings to limit scope.
- Direct overrides for exact paths win over pattern overrides.

## Variant selectors (`oneof_selectors` / `variant_selectors`)

Provide `oneof_selectors` on `Scenario` to choose a `oneOf` **or** `anyOf`
branch deterministically instead of letting the generator pick randomly.

### Key lookup

1. **Exact key** — the key matches `ctx.prop_path` literally.
2. **Regex fallback** — keys are treated as `re.fullmatch` patterns; the
   first matching key (in insertion order) wins.

Use the regex form to target every item in an array at once:

```python
scenario = Scenario(
    name="variants",
    oneof_selectors={
        # exact path: pick index 1 from the oneOf on "pet"
        "pet": 1,

        # regex: apply to items[0], items[1], … — any array index
        r"order\.items\[\d+\]": lambda ctx, schemas: 0,
    },
).normalize()
```

### Selector return values

| Return type | Behaviour |
|---|---|
| `int` | Selects the candidate at that index (bounds-checked, `bool` rejected). |
| `str` | Matched against each candidate's `title`, then the OpenAPI `discriminator` mapping, then `properties[propertyName].const/enum/default`. Raises `ValueError` on no match. |
| `dict` | Taken as the selected schema fragment directly. |

```python
# Select by schema title (works for both oneOf and anyOf)
Scenario(
    name="by_title",
    oneof_selectors={"pet": "Cat"},
).normalize()

# Select by OpenAPI discriminator value
Scenario(
    name="by_disc",
    oneof_selectors={"pet": "cat"},  # matches properties.kind.const == "cat"
).normalize()
```

### Notes
- `normalize()` wraps bare `int`, `str`, and `dict` values into callables.
- The field alias `variant_selectors` is a read-only synonym for
  `oneof_selectors` — both names refer to the same dict.
- `bool` returns from a selector raise `TypeError` (Python's `isinstance(True, int)` gotcha).
- If no selector matches a path, a random candidate is chosen (default behaviour).


## Reusing and composing scenarios
There are two convenient approaches:

1) Keep raw values until the end, merge dicts, then call `normalize()` once.
```python
base = Scenario(name="base", overrides={
    "is_active": True,
})

feature = Scenario(name="feature", overrides={
    "role": "admin",
})

# Compose raw values, then normalize
combined = Scenario(
    name="combined",
    overrides={**base.overrides, **feature.overrides},
    pattern_overrides=[*base.pattern_overrides, *feature.pattern_overrides],
).normalize()
```

2) If you already called `normalize()` on bases, you’re working with callables.
```python
base = Scenario(name="base", overrides={"is_active": True}).normalize()
extra = Scenario(name="extra", overrides={"tier": "gold"}).normalize()

# Merge callable maps (later keys override earlier ones)
reused = Scenario(
    name="reused",
    overrides={**base.overrides, **extra.overrides},
    pattern_overrides=[*base.pattern_overrides, *extra.pattern_overrides],
)
```

Tip: prefer approach (1) for simple authoring. Normalize only at the end just before `generate()`.

## Using scenarios across runs
- Pass a `Scenario` each time: `gen.generate(scenario)`
- Or set a default when creating the generator: `JSONSchemaGenerator(schema, scenario=default_scenario)`

## Arrays and indices in paths
Use bracket notation to target array items when overriding.

```python
Scenario(
    name="array",
    overrides={
        "phones[0].number": "+200000000",
    }
)
```

## Scenario default_data (initialize the result)
You can pre-populate the generated result with default data using the `default_data` field on `Scenario`. These defaults are deep-merged into the result before generation starts, and primitive values from `default_data` are preserved (not overwritten by the generator).

```python
from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema, Scenario

schema = Schema(data={
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "nested": {
            "type": "object",
            "properties": {
                "flag": {"type": "boolean"},
                "count": {"type": "integer"},
            },
        },
    },
})

scenario = Scenario(
    name="with-defaults",
    default_data={
        "name": "Alice",
        "nested": {"flag": True},
    },
)

gen = JSONSchemaGenerator(schema)
result = gen.generate(scenario)

assert result["name"] == "Alice"          # preserved from defaults
assert result["nested"]["flag"] is True   # preserved from defaults
assert isinstance(result["age"], int)       # generator fills in the rest
assert "count" in result["nested"]
```

Behavior notes:
- `default_data` is deep-merged into the result at the start.
- Primitive values present in `default_data` are kept and not overwritten by the generator.
- Object defaults are merged; missing properties are added by the generator.
- Overrides and pattern overrides still apply as usual and can compute values based on the evolving Context.

## Enumerating scenarios for oneOf/anyOf coverage

Use `collect_variant_sites`, `cartesian_scenarios`, and `minimal_scenarios`
from `json_sample_generator` to auto-build a scenario set that covers every
branch in your schema.

```python
from json_sample_generator import (
    JSONSchemaGenerator,
    cartesian_scenarios,
    minimal_scenarios,
)
from json_sample_generator.models import Schema

schema = Schema.from_raw_data(
    {
        "type": "object",
        "properties": {
            "animal": {
                "oneOf": [
                    {"title": "Dog", "type": "object",
                     "properties": {"kind": {"const": "dog"}}},
                    {"title": "Cat", "type": "object",
                     "properties": {"kind": {"const": "cat"}}},
                ]
            },
            "color": {"oneOf": [{"const": "red"}, {"const": "blue"}]},
        },
    },
    base_uri="file://example.json",
)

gen = JSONSchemaGenerator(schema=schema)

# Full cartesian product: 2 × 2 = 4 scenarios
for scenario in cartesian_scenarios(schema):
    print(scenario.name, scenario.description)
    result = gen.generate(scenario)
    print(result)

# Minimal 1-wise cover: max(2, 2) = 2 scenarios
# — every variant of every site appears at least once
for scenario in minimal_scenarios(schema):
    print(scenario.name, scenario.description)
    result = gen.generate(scenario)
    print(result)
```

### API

| Function | Returns | Count |
|---|---|---|
| `collect_variant_sites(schema)` | `list[VariantSite]` | — |
| `cartesian_scenarios(schema, *, name_prefix, base, max_scenarios)` | `list[Scenario]` | `∏ site.count` |
| `minimal_scenarios(schema, *, name_prefix, base)` | `list[Scenario]` | `max(site.count)` |

**`VariantSite` fields:** `path` (e.g. `"animal"` or `"items[*]"`), `kind`
(`"oneOf"` or `"anyOf"`), `count`, `names` (titles/discriminator values, or
`"variant_0"`, `"variant_1"`, …).

**`base` parameter:** pass an existing `Scenario` to inherit its `overrides`,
`pattern_overrides`, and `default_data` on every generated scenario.

**Cartesian cap:** if the product would exceed `max_scenarios` (default
10 000), `cartesian_scenarios` raises `ValueError`. Pass `max_scenarios=N`
to override.

**Nested sites:** sites nested inside oneOf variants are collected
independently. The coverage claim ("every variant appears at least once")
holds per site; whether a nested branch is reachable depends on which outer
variant was selected.

## Minimal mode

Set `minimal_mode=True` on a `Scenario` to generate the smallest valid
sample: only **required** fields (recursively through nested objects,
`allOf`, `oneOf`, `anyOf`) plus any fields you have **explicitly
referenced** in the scenario.

```python
scenario = Scenario(
    name="smoke",
    minimal_mode=True,
    overrides={"desc": "forced"},   # pulls in optional "desc"
)
```

### Inclusion rules (applied per object node)

An optional property `k` at path `P` is kept when any of the following
is true:

| Condition | Detail |
|---|---|
| `k in required` | The parent schema's `required` list contains `k`. |
| Exact override | `scenario.overrides` has a key equal to `P`. |
| Descendant override | Any `overrides` key starts with `P.` or `P[`. |
| `default_data` pre-seeded | The builder already holds a value at `P` (via `default_data`). |
| Selector targets subtree | Any `oneof_selectors` key equals `P` or starts with `P.` / `P[`. |

`pattern_overrides` are **not** forcing — they apply to fields that
survive filtering for other reasons but do not cause optional fields to
appear. Because patterns are substring matches they can be broad; treating
them as forcing would often pull in unintended fields.

### Interaction with other features

- **`allOf`** — `allof_merge` already unions `required` across all
  branches, so the merged schema's `required` list is the authoritative
  source for the minimal filter.
- **`oneOf` / `anyOf`** — variant selection runs first (respecting
  `oneof_selectors`), then the chosen branch's own `required` governs
  which fields appear.
- **Arrays** — the array field itself is subject to the object-level
  filter. Once kept, every item is generated with `minItems`/`maxItems`
  bounds unchanged, and the minimal filter recurses into each item's
  object schema.
- **`max_depth`** and ref resolution — unchanged.
- **`default_data`** — pre-seeded values at a path force that path to be
  kept, and seeded values are preserved in the output.

## Best practices
- Prefer simple values; use callables only when you need context-aware logic.
- Keep scenarios small and composable; merge at the edge.
- Use `pattern_overrides` sparingly and with specific substrings.
- Call `.normalize()` once at the end to avoid accidental mutations.
