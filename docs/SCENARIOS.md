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

## Best practices
- Prefer simple values; use callables only when you need context-aware logic.
- Keep scenarios small and composable; merge at the edge.
- Use `pattern_overrides` sparingly and with specific substrings.
- Call `.normalize()` once at the end to avoid accidental mutations.
