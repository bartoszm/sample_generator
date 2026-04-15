from __future__ import annotations

import pytest

from src.json_sample_generator import (
    JSONSchemaGenerator,
    cartesian_scenarios,
    collect_variant_sites,
    minimal_scenarios,
)
from src.json_sample_generator.models import Scenario, Schema
from src.json_sample_generator.scenario_enum import VariantSite

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schema(**properties) -> Schema:
    """Build a flat object schema with given property sub-schemas."""
    return Schema(data={"type": "object", "properties": dict(properties)})


def _const_oneof(*values) -> dict:
    return {"oneOf": [{"type": "string", "const": v} for v in values]}


def _titled_oneof(*titles) -> dict:
    return {
        "oneOf": [
            {
                "title": t,
                "type": "object",
                "properties": {"which": {"const": t.lower()}},
            }
            for t in titles
        ]
    }


# ---------------------------------------------------------------------------
# collect_variant_sites: basics
# ---------------------------------------------------------------------------


def test_collect_no_sites():
    schema = _make_schema(name={"type": "string"})
    sites = collect_variant_sites(schema)
    assert sites == []


def test_collect_single_oneof():
    schema = _make_schema(pet=_const_oneof("dog", "cat", "bird"))
    sites = collect_variant_sites(schema)
    assert len(sites) == 1
    site = sites[0]
    assert site.path == "pet"
    assert site.kind == "oneOf"
    assert site.count == 3


def test_collect_anyof():
    schema = _make_schema(
        pet={"anyOf": [{"type": "string"}, {"type": "integer"}]}
    )
    sites = collect_variant_sites(schema)
    assert len(sites) == 1
    assert sites[0].kind == "anyOf"
    assert sites[0].count == 2


def test_collect_multiple_sites():
    schema = _make_schema(
        kind=_const_oneof("A", "B", "C"),
        flavor={"anyOf": [{"type": "string"}, {"type": "integer"}]},
    )
    sites = collect_variant_sites(schema)
    paths = {s.path for s in sites}
    assert "kind" in paths and "flavor" in paths
    assert sum(s.count for s in sites) == 5


def test_collect_names_from_title():
    schema = _make_schema(pet=_titled_oneof("Dog", "Cat"))
    sites = collect_variant_sites(schema)
    assert sites[0].names == ("Dog", "Cat")


def test_collect_names_fallback():
    schema = _make_schema(pet=_const_oneof("x", "y"))
    sites = collect_variant_sites(schema)
    # No titles → generic names
    assert sites[0].names == ("variant_0", "variant_1")


def test_collect_allof_site():
    # oneOf buried under allOf that gets merged
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "allOf": [
                        {"description": "base"},
                        _const_oneof("alpha", "beta"),
                    ]
                }
            },
        }
    )
    sites = collect_variant_sites(schema)
    assert any(s.kind == "oneOf" and s.count == 2 for s in sites)


def test_collect_array_items():
    schema = _make_schema(
        items={
            "type": "array",
            "items": _const_oneof("P", "Q"),
        }
    )
    sites = collect_variant_sites(schema)
    assert len(sites) == 1
    # Array-item path uses the [*] wildcard
    assert sites[0].path == "items[*]"
    assert sites[0].count == 2


def test_collect_nested_oneof():
    # Outer oneOf, and variant 0 has a nested oneOf
    schema = _make_schema(
        pet={
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"sub": _const_oneof("x", "y")},
                },
                {"type": "string", "const": "other"},
            ]
        }
    )
    sites = collect_variant_sites(schema)
    paths = {s.path for s in sites}
    assert "pet" in paths
    assert "pet.sub" in paths


def test_collect_dedups_same_path_kind():
    # Both variants of outer oneOf have a nested oneOf at the same path →
    # the inner site is only recorded once.
    schema = _make_schema(
        pet={
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"sub": _const_oneof("A", "B")},
                },
                {
                    "type": "object",
                    "properties": {"sub": _const_oneof("A", "B")},
                },
            ]
        }
    )
    sites = collect_variant_sites(schema)
    sub_sites = [s for s in sites if s.path == "pet.sub"]
    assert len(sub_sites) == 1


# ---------------------------------------------------------------------------
# cartesian_scenarios
# ---------------------------------------------------------------------------


def test_cartesian_count():
    schema = _make_schema(
        kind=_const_oneof("A", "B", "C"),
        flavor=_const_oneof("X", "Y"),
    )
    scenarios = cartesian_scenarios(schema)
    assert len(scenarios) == 6  # 3 × 2


def test_cartesian_all_distinct():
    schema = _make_schema(
        kind=_const_oneof("A", "B"),
        flavor=_const_oneof("X", "Y"),
    )
    scenarios = cartesian_scenarios(schema)
    selector_combos = [
        tuple(sorted(s.oneof_selectors.items())) for s in scenarios
    ]
    assert len(set(selector_combos)) == 4


def test_cartesian_no_sites_returns_one():
    schema = _make_schema(name={"type": "string"})
    scenarios = cartesian_scenarios(schema)
    assert len(scenarios) == 1
    assert isinstance(scenarios[0], Scenario)


def test_cartesian_respects_name_prefix():
    schema = _make_schema(pet=_const_oneof("A", "B"))
    scenarios = cartesian_scenarios(schema, name_prefix="combo")
    assert all(s.name.startswith("combo_") for s in scenarios)


def test_cartesian_max_scenarios_raises():
    schema = _make_schema(
        a=_const_oneof("1", "2", "3"),
        b=_const_oneof("x", "y", "z"),
    )
    with pytest.raises(ValueError, match="max_scenarios"):
        cartesian_scenarios(schema, max_scenarios=5)


def test_cartesian_base_overrides_survive():
    base = Scenario(name="base", overrides={"name": lambda ctx: "fixed"})
    schema = _make_schema(
        name={"type": "string"},
        pet=_const_oneof("A", "B"),
    )
    scenarios = cartesian_scenarios(schema, base=base)
    # Every generated scenario should carry the override
    assert all("name" in s.overrides for s in scenarios)


# ---------------------------------------------------------------------------
# minimal_scenarios
# ---------------------------------------------------------------------------


def _all_covered(sites, scenarios) -> bool:
    """Return True when every (site_index, variant_index) is selected
    in at least one scenario."""
    for i, site in enumerate(sites):
        for var_idx in range(site.count):
            covered = any(
                # After normalize(), the selector is a callable.
                # We can't easily inspect it, so run a dummy call.
                _selector_index(s, site.path, site, var_idx)
                for s in scenarios
            )
            if not covered:
                return False
    return True


def _selector_index(
    scenario: Scenario, path: str, site: VariantSite, expected_idx: int
) -> bool:
    """Return True if the scenario's selector at path picks expected_idx."""
    from src.json_sample_generator.JSONSchemaGenerator import (
        JSONSchemaGenerator,
    )
    from src.json_sample_generator.models import Context

    # Build a minimal context to call the selector
    ctx = Context(
        prop_path=path,
        data={},
        schema_data={},
    )
    dummy_schemas = [{} for _ in range(site.count)]
    sel = JSONSchemaGenerator._lookup_variant_selector(path, scenario)
    if sel is None:
        return False
    result = sel(ctx, dummy_schemas)
    return result == expected_idx


def test_minimal_count():
    schema = _make_schema(
        kind=_const_oneof("A", "B", "C"),  # count=3
        flavor=_const_oneof("X", "Y"),  # count=2
    )
    scenarios = minimal_scenarios(schema)
    assert len(scenarios) == 3  # max(3, 2)


def test_minimal_covers_all_variants():
    schema = _make_schema(
        kind=_const_oneof("A", "B", "C"),
        flavor=_const_oneof("X", "Y"),
    )
    sites = collect_variant_sites(schema)
    scenarios = minimal_scenarios(schema)
    assert _all_covered(sites, scenarios)


def test_minimal_single_site():
    schema = _make_schema(pet=_const_oneof("A", "B", "C", "D"))
    scenarios = minimal_scenarios(schema)
    assert len(scenarios) == 4
    sites = collect_variant_sites(schema)
    assert _all_covered(sites, scenarios)


def test_minimal_no_sites_returns_one():
    schema = _make_schema(name={"type": "string"})
    scenarios = minimal_scenarios(schema)
    assert len(scenarios) == 1


def test_minimal_respects_name_prefix():
    schema = _make_schema(pet=_const_oneof("A", "B"))
    scenarios = minimal_scenarios(schema, name_prefix="min")
    assert all(s.name.startswith("min_") for s in scenarios)


def test_minimal_base_overrides_survive():
    base = Scenario(name="base", overrides={"x": lambda ctx: 99})
    schema = _make_schema(pet=_const_oneof("A", "B"))
    scenarios = minimal_scenarios(schema, base=base)
    assert all("x" in s.overrides for s in scenarios)


# ---------------------------------------------------------------------------
# End-to-end: generate with enumerated scenarios
# ---------------------------------------------------------------------------


def test_e2e_cartesian_hits_all_branches():
    schema = _make_schema(pet=_titled_oneof("Dog", "Cat"))
    gen = JSONSchemaGenerator(schema=schema)
    results = [gen.generate(s) for s in cartesian_scenarios(schema)]
    seen = {r["pet"]["which"] for r in results}
    assert seen == {"dog", "cat"}


def test_e2e_minimal_hits_all_branches():
    schema = _make_schema(pet=_titled_oneof("Dog", "Cat", "Bird"))
    gen = JSONSchemaGenerator(schema=schema)
    results = [gen.generate(s) for s in minimal_scenarios(schema)]
    seen = {r["pet"]["which"] for r in results}
    assert seen == {"dog", "cat", "bird"}


def test_e2e_cartesian_two_sites():
    schema = _make_schema(
        animal=_titled_oneof("Dog", "Cat"),
        color=_const_oneof("red", "blue"),
    )
    gen = JSONSchemaGenerator(schema=schema)
    scenarios = cartesian_scenarios(schema)
    assert len(scenarios) == 4

    combos = set()
    for s in scenarios:
        r = gen.generate(s)
        combos.add((r["animal"]["which"], r["color"]))
    expected = {
        ("dog", "red"),
        ("dog", "blue"),
        ("cat", "red"),
        ("cat", "blue"),
    }
    assert combos == expected


def test_e2e_array_site():
    schema = _make_schema(
        items={
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": _const_oneof("A", "B"),
        }
    )
    gen = JSONSchemaGenerator(schema=schema)
    for s in minimal_scenarios(schema):
        result = gen.generate(s)
        # Both items should use the same selector (array regex key)
        assert result["items"][0] == result["items"][1]


def test_e2e_base_scenario_overrides_honoured():
    base = Scenario(name="b", overrides={"note": lambda ctx: "hello"})
    schema = _make_schema(
        note={"type": "string"},
        pet=_titled_oneof("Dog", "Cat"),
    )
    gen = JSONSchemaGenerator(schema=schema)
    for s in minimal_scenarios(schema, base=base):
        r = gen.generate(s)
        assert r["note"] == "hello"
