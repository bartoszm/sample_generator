"""The scenario and break enumerators render paths like the generator
and stop at recursion."""

from __future__ import annotations

import time

import pytest

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.break_enum import collect_break_sites
from json_sample_generator.breaker import SampleBreaker
from json_sample_generator.helpers.utils import parse_path
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


RECURSIVE = {
    "type": "object",
    "required": ["kind", "next"],
    "properties": {
        "kind": {"oneOf": [{"const": "x"}, {"const": "y"}]},
        "next": {"$ref": "#"},
        "extra": {"oneOf": [{"const": 1}, {"const": 2}]},
    },
}


def test_enumerators_mirror_the_generator_recursion_rule():
    # Schema.from_raw_data resolves the $ref, so the walkers really recurse.
    schema = Schema.from_raw_data(RECURSIVE, "file://rec.json")
    started = time.perf_counter()
    variant_paths = {s.path for s in collect_variant_sites(schema)}
    break_paths = {s.path for s in collect_break_sites(schema)}
    assert time.perf_counter() - started < 2
    # next: first occurrence of "#", walked in full; next.next: second,
    # required members only (so no next.next.extra); next.next.next: cut
    assert variant_paths == {
        "kind",
        "extra",
        "next.kind",
        "next.extra",
        "next.next.kind",
    }
    assert "next.next.kind" in break_paths
    assert not any(
        p.startswith("next.next.next") or p == "next.next.extra"
        for p in break_paths
    )
    # ...which is exactly what the generator produces (it resolves the
    # refs itself; an already-resolved recursive schema would make jsonref
    # recurse without end)
    gen = JSONSchemaGenerator(
        Schema(data=RECURSIVE, base_uri="file://rec.json")
    )
    with pytest.warns(UserWarning, match="recursion limit"):
        out = gen.generate()
    assert set(out["next"]) == {"kind", "next", "extra"}
    assert set(out["next"]["next"]) == {"kind"}


def test_enumerators_prune_optional_recursion():
    raw = {
        "type": "object",
        "properties": {
            "kind": {"oneOf": [{"const": "x"}, {"const": "y"}]},
            "left": {"$ref": "#"},
            "right": {"$ref": "#"},
        },
    }
    schema = Schema.from_raw_data(raw, "file://rec.json")
    # left/right: first occurrence, walked in full; left.left etc.: second,
    # required members only, and nothing is required, so no deeper sites
    assert {s.path for s in collect_variant_sites(schema)} == {
        "kind",
        "left.kind",
        "right.kind",
    }
    assert all(
        len(parse_path(s.path)) <= 2 for s in collect_break_sites(schema)
    )
    out = JSONSchemaGenerator(
        Schema(data=raw, base_uri="file://rec.json")
    ).generate()
    assert "kind" in out["left"]
    assert out["left"]["left"] == {} and "kind" not in out["left"]["left"]
