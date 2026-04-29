"""Tests for the break-scenarios feature.

Coverage:
- Each BreakKind produces an invalid sample validated by jsonschema.
- collect_break_sites shape (paths, applicable kinds).
- enumerate_break_scenarios: one rule per (site, kind), max_scenarios cap.
- random_break_scenario: deterministic with seed, raises on excess.
- merge_break_scenarios: concatenates rules.
- End-to-end: generate → break → jsonschema.validate raises.
- oneOf-resolution: WRONG_TYPE on a property reachable only in branch B.
"""

from __future__ import annotations

import jsonschema
import pytest

from json_sample_generator import (
    BreakKind,
    BreakRule,
    BreakScenario,
    BreakScenarioReport,
    JSONSchemaGenerator,
    RuleCheck,
    SampleBreaker,
    apply_break_scenario,
    check_break_scenario,
    collect_break_sites,
    enumerate_break_scenarios,
    merge_break_scenarios,
    random_break_scenario,
    validate_breaks,
)
from json_sample_generator.models.models import Schema

# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

_FULL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 2,
            "maxLength": 50,
        },
        "email": {"type": "string", "format": "email"},
        "code": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "status": {"type": "string", "enum": ["active", "inactive"]},
        "kind": {"type": "string", "const": "user"},
        "age": {"type": "integer", "minimum": 0, "maximum": 150},
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 5,
        },
        "address": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
            },
            "additionalProperties": False,
            "required": ["street"],
        },
    },
    "required": ["name", "status", "kind"],
}

_FULL_SAMPLE = {
    "name": "Alice",
    "email": "alice@example.com",
    "code": "ABC",
    "status": "active",
    "kind": "user",
    "age": 30,
    "score": 0.75,
    "tags": ["a", "b"],
    "address": {"street": "Main St"},
}

_ONEOF_SCHEMA = {
    "type": "object",
    "oneOf": [
        {
            "properties": {"branch": {"type": "string", "const": "A"}},
            "required": ["branch"],
        },
        {
            "properties": {
                "branch": {"type": "string", "const": "B"},
                "b_only": {"type": "integer"},
            },
            "required": ["branch", "b_only"],
        },
    ],
}


def _schema(data: dict) -> Schema:
    return Schema(data=data)


def _validate_fails(schema_data: dict, sample: dict) -> None:
    """Assert that *sample* does NOT pass jsonschema validation."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(sample, schema_data)


def _validate_ok(schema_data: dict, sample: dict) -> None:
    """Assert that *sample* passes jsonschema validation."""
    jsonschema.validate(sample, schema_data)


# ---------------------------------------------------------------------------
# Individual BreakKind tests
# ---------------------------------------------------------------------------


def test_wrong_type():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.WRONG_TYPE)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert not isinstance(broken["name"], str)


def test_remove_required():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.REMOVE_REQUIRED)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert "name" not in broken
    _validate_fails(_FULL_SCHEMA, broken)


def test_null_value():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.NULL_VALUE)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["name"] is None
    _validate_fails(_FULL_SCHEMA, broken)


def test_enum_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="status", kind=BreakKind.ENUM_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["status"] not in ("active", "inactive")
    _validate_fails(_FULL_SCHEMA, broken)


def test_const_violation_string():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="kind", kind=BreakKind.CONST_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["kind"] != "user"
    _validate_fails(_FULL_SCHEMA, broken)


def test_pattern_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="code", kind=BreakKind.PATTERN_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["code"].startswith("!!!")
    _validate_fails(_FULL_SCHEMA, broken)


def test_min_length_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.MIN_LENGTH_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert len(broken["name"]) < 2
    _validate_fails(_FULL_SCHEMA, broken)


def test_max_length_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.MAX_LENGTH_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert len(broken["name"]) > 50
    _validate_fails(_FULL_SCHEMA, broken)


def test_min_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="age", kind=BreakKind.MIN_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["age"] < 0
    _validate_fails(_FULL_SCHEMA, broken)


def test_max_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="age", kind=BreakKind.MAX_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["age"] > 150
    _validate_fails(_FULL_SCHEMA, broken)


def test_additional_property():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="address", kind=BreakKind.ADDITIONAL_PROPERTY)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert "__break_extra__" in broken["address"]
    _validate_fails(_FULL_SCHEMA, broken)


def test_min_items_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="tags", kind=BreakKind.MIN_ITEMS_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert len(broken["tags"]) < 1
    _validate_fails(_FULL_SCHEMA, broken)


def test_max_items_violation():
    sample = dict(_FULL_SAMPLE)
    sample["tags"] = ["a"]
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="tags", kind=BreakKind.MAX_ITEMS_VIOLATION)],
    )
    broken = breaker.apply(sample, scenario)
    assert len(broken["tags"]) > 5
    _validate_fails(_FULL_SCHEMA, broken)


def test_format_violation():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="email", kind=BreakKind.FORMAT_VIOLATION)],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["email"] == "not-an-email"


def test_explicit_value_overrides_auto():
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[
            BreakRule(
                path="name",
                kind=BreakKind.WRONG_TYPE,
                value=12345,
            )
        ],
    )
    broken = breaker.apply(_FULL_SAMPLE, scenario)
    assert broken["name"] == 12345


def test_original_sample_unchanged():
    import copy

    original = copy.deepcopy(_FULL_SAMPLE)
    breaker = SampleBreaker(_schema(_FULL_SCHEMA))
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.NULL_VALUE)],
    )
    breaker.apply(_FULL_SAMPLE, scenario)
    assert _FULL_SAMPLE == original


# ---------------------------------------------------------------------------
# collect_break_sites
# ---------------------------------------------------------------------------


def test_collect_break_sites_paths():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    paths = {s.path for s in sites}
    assert "name" in paths
    assert "age" in paths
    assert "status" in paths
    assert "tags" in paths
    assert "address.street" in paths


def test_collect_break_sites_required_flag():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    name_site = next(s for s in sites if s.path == "name")
    assert name_site.required_in_parent is True
    assert BreakKind.REMOVE_REQUIRED in name_site.applicable


def test_collect_break_sites_additional_props_flag():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    street_site = next(s for s in sites if s.path == "address.street")
    assert street_site.parent_additional_props_false is True
    assert BreakKind.ADDITIONAL_PROPERTY in street_site.applicable


def test_collect_break_sites_enum_kind():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    status_site = next(s for s in sites if s.path == "status")
    assert BreakKind.ENUM_VIOLATION in status_site.applicable


def test_collect_break_sites_numeric_bounds():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    age_site = next(s for s in sites if s.path == "age")
    assert BreakKind.MIN_VIOLATION in age_site.applicable
    assert BreakKind.MAX_VIOLATION in age_site.applicable


def test_collect_break_sites_format():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    email_site = next(s for s in sites if s.path == "email")
    assert BreakKind.FORMAT_VIOLATION in email_site.applicable


def test_collect_break_sites_oneof():
    sites = collect_break_sites(_schema(_ONEOF_SCHEMA))
    paths = {s.path for s in sites}
    # Both branches should be discovered.
    assert "branch" in paths
    assert "b_only" in paths


# ---------------------------------------------------------------------------
# enumerate_break_scenarios
# ---------------------------------------------------------------------------


def test_enumerate_break_scenarios_one_rule_each():
    scenarios = enumerate_break_scenarios(_schema(_FULL_SCHEMA))
    for s in scenarios:
        assert len(s.rules) == 1
        assert s.expected_failure_count == 1


def test_enumerate_break_scenarios_count():
    sites = collect_break_sites(_schema(_FULL_SCHEMA))
    expected = sum(len(s.applicable) for s in sites)
    scenarios = enumerate_break_scenarios(_schema(_FULL_SCHEMA))
    assert len(scenarios) == expected


def test_enumerate_break_scenarios_max_cap():
    with pytest.raises(ValueError, match="max_scenarios"):
        enumerate_break_scenarios(_schema(_FULL_SCHEMA), max_scenarios=1)


def test_enumerate_break_scenarios_unique_names():
    scenarios = enumerate_break_scenarios(_schema(_FULL_SCHEMA))
    names = [s.name for s in scenarios]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# random_break_scenario
# ---------------------------------------------------------------------------


def test_random_break_scenario_deterministic():
    schema = _schema(_FULL_SCHEMA)
    s1 = random_break_scenario(schema, num_failures=3, seed=42)
    s2 = random_break_scenario(schema, num_failures=3, seed=42)
    assert s1.rules == s2.rules


def test_random_break_scenario_different_seeds():
    schema = _schema(_FULL_SCHEMA)
    s1 = random_break_scenario(schema, num_failures=3, seed=1)
    s2 = random_break_scenario(schema, num_failures=3, seed=2)
    # Very unlikely to be identical with different seeds.
    assert s1.rules != s2.rules


def test_random_break_scenario_count():
    schema = _schema(_FULL_SCHEMA)
    scenario = random_break_scenario(schema, num_failures=4, seed=0)
    assert len(scenario.rules) == 4


def test_random_break_scenario_too_many():
    schema = _schema(
        {"type": "object", "properties": {"x": {"type": "string"}}}
    )
    sites = collect_break_sites(schema)
    with pytest.raises(ValueError, match="num_failures"):
        random_break_scenario(schema, num_failures=len(sites) + 1)


# ---------------------------------------------------------------------------
# merge_break_scenarios
# ---------------------------------------------------------------------------


def test_merge_break_scenarios_concatenates_rules():
    s1 = BreakScenario(
        name="a",
        rules=[BreakRule(path="name", kind=BreakKind.NULL_VALUE)],
        expected_failure_count=1,
    )
    s2 = BreakScenario(
        name="b",
        rules=[BreakRule(path="status", kind=BreakKind.ENUM_VIOLATION)],
        expected_failure_count=1,
    )
    merged = merge_break_scenarios(s1, s2, name="merged")
    assert len(merged.rules) == 2
    assert merged.expected_failure_count == 2
    assert merged.name == "merged"


def test_merge_break_scenarios_applies_all_breaks():
    s1 = BreakScenario(
        name="a",
        rules=[BreakRule(path="name", kind=BreakKind.NULL_VALUE)],
    )
    s2 = BreakScenario(
        name="b",
        rules=[BreakRule(path="status", kind=BreakKind.ENUM_VIOLATION)],
    )
    merged = merge_break_scenarios(s1, s2, name="merged")
    broken = apply_break_scenario(_schema(_FULL_SCHEMA), _FULL_SAMPLE, merged)
    assert broken["name"] is None
    assert broken["status"] not in ("active", "inactive")


def test_merge_break_scenarios_none_count_propagates():
    s1 = BreakScenario(
        name="a",
        rules=[BreakRule(path="name", kind=BreakKind.NULL_VALUE)],
        expected_failure_count=None,
    )
    s2 = BreakScenario(
        name="b",
        rules=[BreakRule(path="status", kind=BreakKind.ENUM_VIOLATION)],
        expected_failure_count=1,
    )
    merged = merge_break_scenarios(s1, s2, name="merged")
    assert merged.expected_failure_count is None


# ---------------------------------------------------------------------------
# validate_breaks
# ---------------------------------------------------------------------------


def test_validate_breaks_matched():
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="name", kind=BreakKind.REMOVE_REQUIRED)],
    )
    broken = apply_break_scenario(
        _schema(_FULL_SCHEMA), _FULL_SAMPLE, scenario
    )
    failures = validate_breaks(_schema(_FULL_SCHEMA), broken, scenario)
    assert len(failures) == 1
    assert failures[0].matched


def test_validate_breaks_unmatched_noop():
    # An unreachable path should not match any errors.
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="nonexistent_field", kind=BreakKind.NULL_VALUE)],
    )
    broken = apply_break_scenario(
        _schema(_FULL_SCHEMA), _FULL_SAMPLE, scenario
    )
    failures = validate_breaks(_schema(_FULL_SCHEMA), broken, scenario)
    assert not failures[0].matched


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_end_to_end_generate_break_validate():
    schema_data = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string", "minLength": 3},
        },
        "required": ["id", "name"],
    }
    schema = _schema(schema_data)
    sample = JSONSchemaGenerator(schema=schema).generate()
    _validate_ok(schema_data, sample)

    scenario = BreakScenario(
        name="break_name",
        rules=[BreakRule(path="name", kind=BreakKind.MIN_LENGTH_VIOLATION)],
    )
    broken = apply_break_scenario(schema, sample, scenario)
    _validate_fails(schema_data, broken)


# ---------------------------------------------------------------------------
# oneOf-resolution
# ---------------------------------------------------------------------------


def test_oneof_wrong_type_on_branch_b():
    sample_b = {"branch": "B", "b_only": 42}
    schema = _schema(_ONEOF_SCHEMA)
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="b_only", kind=BreakKind.WRONG_TYPE)],
    )
    broken = apply_break_scenario(schema, sample_b, scenario)
    assert not isinstance(broken["b_only"], int)


def test_oneof_break_on_branch_a_doesnt_touch_b():
    sample_a = {"branch": "A"}
    schema = _schema(_ONEOF_SCHEMA)
    # WRONG_TYPE on b_only: that key doesn't exist in sample_a — no-op.
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path="b_only", kind=BreakKind.WRONG_TYPE)],
    )
    broken = apply_break_scenario(schema, sample_a, scenario)
    assert "b_only" not in broken


# ---------------------------------------------------------------------------
# check_break_scenario — static validator
# ---------------------------------------------------------------------------


def test_check_path_not_found():
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="nonexistent", kind=BreakKind.NULL_VALUE)],
        ),
    )
    assert len(report.checks) == 1
    check = report.checks[0]
    assert not check.applicable
    assert "path not found" in check.reason
    assert check.matched_path is None
    assert check.schema_fragment is None
    assert check.available_kinds == ()


def test_check_kind_incompatible_enum():
    # "name" has no enum constraint
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="name", kind=BreakKind.ENUM_VIOLATION)],
        ),
    )
    check = report.checks[0]
    assert not check.applicable
    assert "enum" in check.reason
    assert BreakKind.ENUM_VIOLATION not in check.available_kinds


def test_check_kind_incompatible_remove_required():
    # "email" exists in schema but is not in required
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="email", kind=BreakKind.REMOVE_REQUIRED)],
        ),
    )
    check = report.checks[0]
    assert not check.applicable
    assert "required" in check.reason


def test_check_kind_incompatible_additional_property():
    # "name" is a string, its parent doesn't have additionalProperties:false
    report = check_break_scenario(
        _schema(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        ),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="name", kind=BreakKind.ADDITIONAL_PROPERTY)],
        ),
    )
    check = report.checks[0]
    assert not check.applicable
    assert "additionalProperties" in check.reason


def test_check_kind_incompatible_min_length_on_integer():
    # "age" is an integer — MIN_LENGTH_VIOLATION requires a string
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="age", kind=BreakKind.MIN_LENGTH_VIOLATION)],
        ),
    )
    check = report.checks[0]
    assert not check.applicable
    assert "minLength" in check.reason


def test_check_valid_rule():
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="name", kind=BreakKind.WRONG_TYPE)],
        ),
    )
    check = report.checks[0]
    assert check.applicable
    assert check.reason == "ok"
    assert check.matched_path == "name"
    assert check.schema_fragment is not None
    assert BreakKind.WRONG_TYPE in check.available_kinds


def test_check_valid_required_rule():
    # "name" IS in required — REMOVE_REQUIRED should be applicable
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="name", kind=BreakKind.REMOVE_REQUIRED)],
        ),
    )
    assert report.checks[0].applicable


def test_check_valid_additional_property_rule():
    # "address.street" has parent with additionalProperties:false
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[
                BreakRule(
                    path="address.street",
                    kind=BreakKind.ADDITIONAL_PROPERTY,
                )
            ],
        ),
    )
    assert report.checks[0].applicable


def test_check_normalizes_indices():
    # items[0] should match the items[*] site in the schema
    schema_data = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            }
        },
    }
    report = check_break_scenario(
        _schema(schema_data),
        BreakScenario(
            name="t",
            rules=[
                BreakRule(
                    path="tags[0]",
                    kind=BreakKind.MIN_LENGTH_VIOLATION,
                )
            ],
        ),
    )
    check = report.checks[0]
    assert check.applicable
    assert check.matched_path == "tags[*]"


def test_check_aggregates_oneof_branches():
    # When a property appears in multiple oneOf branches, collect_break_sites
    # deduplicates by path (first branch wins).  A kind valid in ANY matching
    # site is considered applicable.  Here both branches have "x", and the
    # first branch (plain string, no enum) is recorded — so ENUM_VIOLATION
    # is NOT applicable, while WRONG_TYPE is.
    schema_data = {
        "type": "object",
        "oneOf": [
            {
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
            {
                "properties": {"x": {"type": "string", "enum": ["a", "b"]}},
                "required": ["x"],
            },
        ],
    }
    report_wrong_type = check_break_scenario(
        _schema(schema_data),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="x", kind=BreakKind.WRONG_TYPE)],
        ),
    )
    assert report_wrong_type.checks[0].applicable

    # ENUM_VIOLATION not applicable — the plain-string branch was recorded.
    report_enum = check_break_scenario(
        _schema(schema_data),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="x", kind=BreakKind.ENUM_VIOLATION)],
        ),
    )
    assert not report_enum.checks[0].applicable


def test_check_all_applicable_false_on_mixed():
    scenario = BreakScenario(
        name="mixed",
        rules=[
            BreakRule(path="name", kind=BreakKind.WRONG_TYPE),  # ok
            BreakRule(path="name", kind=BreakKind.ENUM_VIOLATION),  # no enum
        ],
    )
    report = check_break_scenario(_schema(_FULL_SCHEMA), scenario)
    assert not report.all_applicable
    assert report.checks[0].applicable
    assert not report.checks[1].applicable


def test_check_all_applicable_true_on_valid():
    scenario = BreakScenario(
        name="all_good",
        rules=[
            BreakRule(path="name", kind=BreakKind.WRONG_TYPE),
            BreakRule(path="status", kind=BreakKind.ENUM_VIOLATION),
            BreakRule(path="age", kind=BreakKind.MIN_VIOLATION),
        ],
    )
    report = check_break_scenario(_schema(_FULL_SCHEMA), scenario)
    assert report.all_applicable
    assert report.scenario_name == "all_good"


def test_check_report_type():
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(name="t", rules=[]),
    )
    assert isinstance(report, BreakScenarioReport)
    assert isinstance(report.checks, list)


def test_check_rule_check_type():
    report = check_break_scenario(
        _schema(_FULL_SCHEMA),
        BreakScenario(
            name="t",
            rules=[BreakRule(path="name", kind=BreakKind.WRONG_TYPE)],
        ),
    )
    assert isinstance(report.checks[0], RuleCheck)


def test_check_enumerated_scenarios_all_applicable():
    # Every scenario produced by enumerate_break_scenarios must pass the check.
    scenarios = enumerate_break_scenarios(_schema(_FULL_SCHEMA))
    for scenario in scenarios:
        report = check_break_scenario(_schema(_FULL_SCHEMA), scenario)
        assert (
            report.all_applicable
        ), f"Scenario {scenario.name!r} failed check: " + "; ".join(
            c.reason for c in report.checks if not c.applicable
        )
