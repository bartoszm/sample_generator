"""Break scenarios example.

Shows the full workflow:
1. Generate a valid sample from a schema.
2. Build a random break scenario.
3. Apply it to produce an invalid sample.
4. Use validate_breaks to confirm which rules triggered errors.
"""

from __future__ import annotations

import json

import jsonschema

from json_sample_generator import (
    BreakKind,
    BreakRule,
    BreakScenario,
    JSONSchemaGenerator,
    apply_break_scenario,
    collect_break_sites,
    enumerate_break_scenarios,
    merge_break_scenarios,
    random_break_scenario,
    validate_breaks,
)
from json_sample_generator.models.models import Schema

SCHEMA_DATA = {
    "type": "object",
    "properties": {
        "username": {
            "type": "string",
            "minLength": 3,
            "maxLength": 20,
        },
        "email": {"type": "string", "format": "email"},
        "role": {
            "type": "string",
            "enum": ["admin", "editor", "viewer"],
        },
        "age": {"type": "integer", "minimum": 0, "maximum": 120},
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "active": {"type": "boolean"},
        "address": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "zip": {
                    "type": "string",
                    "pattern": r"^\d{5}$",
                },
            },
            "additionalProperties": False,
            "required": ["city"],
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
        },
    },
    "required": ["username", "email", "role"],
}

schema = Schema(data=SCHEMA_DATA)

# --- 1. Generate a valid sample ------------------------------------------

generator = JSONSchemaGenerator(schema=schema)
valid_sample = generator.generate()

print("=== Valid sample ===")
print(json.dumps(valid_sample, indent=2, default=str))
try:
    jsonschema.validate(valid_sample, SCHEMA_DATA)
    print("✓  Passes validation\n")
except jsonschema.ValidationError as e:
    print(f"✗  Validation error: {e.message}\n")

# --- 2. Enumerate all possible single-break scenarios --------------------

all_scenarios = enumerate_break_scenarios(schema)
print(f"=== Break sites: {len(collect_break_sites(schema))} sites found ===")
print(
    f"=== enumerate_break_scenarios: {len(all_scenarios)} single-break "
    "scenarios ===\n"
)
for s in all_scenarios[:5]:
    print(f"  {s.name}: {s.description}")
if len(all_scenarios) > 5:
    print(f"  … and {len(all_scenarios) - 5} more")
print()

# --- 3. Random break scenario (reproducible with seed) -------------------

rand_scenario = random_break_scenario(schema, num_failures=2, seed=42)
print(f"=== Random break scenario: {rand_scenario.name} ===")
for rule in rand_scenario.rules:
    print(f"  path={rule.path!r}  kind={rule.kind.value}")
print()

broken = apply_break_scenario(schema, valid_sample, rand_scenario)
print("=== Broken sample ===")
print(json.dumps(broken, indent=2, default=str))

failures = validate_breaks(schema, broken, rand_scenario)
print("\n=== validate_breaks report ===")
for f in failures:
    status = "MATCHED" if f.matched else "no-op"
    print(f"  [{status}] {f.rule.path!r} ({f.rule.kind.value})")
    for err in f.matched_errors:
        print(f"    → {err.message}")
print()

# --- 4. Compose a multi-break scenario with merge_break_scenarios --------

remove_username = BreakScenario(
    name="remove_required_username",
    rules=[BreakRule(path="username", kind=BreakKind.REMOVE_REQUIRED)],
    expected_failure_count=1,
)
bad_email = BreakScenario(
    name="bad_email_format",
    rules=[BreakRule(path="email", kind=BreakKind.FORMAT_VIOLATION)],
    expected_failure_count=1,
)
combined = merge_break_scenarios(
    remove_username,
    bad_email,
    name="combined_two_breaks",
    description="Remove required field + invalid format",
)
print(f"=== Merged scenario: {combined.name} ===")
print(
    f"  {len(combined.rules)} rules, "
    f"expected_failure_count={combined.expected_failure_count}"
)
multi_broken = apply_break_scenario(schema, valid_sample, combined)
multi_failures = validate_breaks(schema, multi_broken, combined)
for f in multi_failures:
    status = "MATCHED" if f.matched else "no-op"
    print(f"  [{status}] {f.rule.path!r} ({f.rule.kind.value})")
    for err in f.matched_errors:
        print(f"    → {err.message}")
