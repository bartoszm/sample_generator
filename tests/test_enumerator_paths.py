"""The scenario and break enumerators render paths like the generator
and stop at recursion."""

from __future__ import annotations

import time

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.break_enum import collect_break_sites
from json_sample_generator.breaker import SampleBreaker
from json_sample_generator.models import Schema
from json_sample_generator.models.break_models import (
    BreakKind,
    BreakRule,
    BreakScenario,
)
from json_sample_generator.scenario_enum import (
    cartesian_scenarios,
    collect_variant_sites,
)

DOTTED = Schema(
    data={
        "type": "object",
        "properties": {
            "a.b": {
                "oneOf": [
                    {"type": "string", "const": "P"},
                    {"type": "string", "const": "Q"},
                ]
            }
        },
        "required": ["a.b"],
    }
)


def test_variant_sites_use_quoted_keys():
    assert [s.path for s in collect_variant_sites(DOTTED)] == ['["a.b"]']


def test_cartesian_scenarios_select_variants_under_a_dotted_key():
    scenarios = cartesian_scenarios(DOTTED)
    assert len(scenarios) == 2
    gen = JSONSchemaGenerator(DOTTED)
    assert {gen.generate(s)["a.b"] for s in scenarios} == {"P", "Q"}


def test_break_sites_use_quoted_keys_and_apply():
    schema = Schema(
        data={
            "type": "object",
            "properties": {"a.b": {"type": "string", "maxLength": 3}},
        }
    )
    sites = collect_break_sites(schema)
    assert any(s.path == '["a.b"]' for s in sites)
    scenario = BreakScenario(
        name="t",
        rules=[BreakRule(path='["a.b"]', kind=BreakKind.MAX_LENGTH_VIOLATION)],
    )
    assert SampleBreaker(schema).apply({"a.b": "ok"}, scenario) == {
        "a.b": "xxxx"
    }


def test_enumerators_stop_at_recursion():
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "kind": {"oneOf": [{"const": "x"}, {"const": "y"}]},
                "left": {"$ref": "#"},
                "right": {"$ref": "#"},
            },
        },
        base_uri="file://rec.json",
    )
    started = time.perf_counter()
    variant_sites = collect_variant_sites(schema)
    break_sites = collect_break_sites(schema)
    assert time.perf_counter() - started < 2
    assert [s.path for s in variant_sites] == ["kind"]
    assert all(
        s.path.count("left") + s.path.count("right") <= 1 for s in break_sites
    )
