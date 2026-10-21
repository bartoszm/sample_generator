"""Result assembly: empty containers are emitted, nested and root arrays
and dotted property names work, ``ctx.data`` is a live view with
forward references deferred, ``uniqueItems`` is honoured, recursion ends
through the cycle rule and ``max_depth`` is only a hard cap."""

from __future__ import annotations

import random
import time
import warnings

import pytest
from faker import Faker
from jsonschema import Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.models import Scenario, Schema


def _obj(**props):
    return {"type": "object", "properties": props, "required": list(props)}


def _generate_many(schema, n=30, scenario=None, validate=True, **kwargs):
    """Generate *n* seeded samples, assert each validates, return them."""
    gen = JSONSchemaGenerator(Schema(data=schema), **kwargs)
    validator = Draft7Validator(
        schema, format_checker=Draft7Validator.FORMAT_CHECKER
    )
    outputs = []
    for seed in range(n):
        random.seed(seed)
        Faker.seed(seed)
        out = gen.generate(scenario)
        if validate:
            errors = [e.message for e in validator.iter_errors(out)]
            assert not errors, (seed, out, errors)
        outputs.append(out)
    return outputs


# ---------------------------------------------------------------------------
# Empty containers (issue 3)
# ---------------------------------------------------------------------------
def test_required_object_without_properties_is_present():
    for out in _generate_many(_obj(meta={"type": "object"})):
        assert out == {"meta": {}}


def test_required_array_that_draws_zero_items_is_present():
    schema = _obj(tags={"type": "array", "items": {"type": "string"}})
    outputs = _generate_many(schema)
    assert all(isinstance(out["tags"], list) for out in outputs)
    assert any(out["tags"] == [] for out in outputs)


def test_minimal_mode_required_object_with_only_optional_properties():
    schema = _obj(
        size={"type": "object", "properties": {"width": {"type": "number"}}}
    )
    scenario = Scenario(name="m", minimal_mode=True)
    for out in _generate_many(schema, scenario=scenario):
        assert out == {"size": {}}


def test_minimal_mode_required_array_of_objects_with_optional_properties():
    schema = _obj(
        parts={
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}},
            },
        }
    )
    scenario = Scenario(name="m", minimal_mode=True)
    for out in _generate_many(schema, scenario=scenario):
        assert out["parts"] and all(part == {} for part in out["parts"])


def test_scenario_only_keeps_uncovered_containers_absent():
    schema = _obj(meta={"type": "object"}, id={"type": "string"})
    gen = JSONSchemaGenerator(Schema(data=schema))
    out = gen.generate(
        Scenario(name="s", scenario_only=True, overrides={"id": "1"})
    )
    assert out == {"id": "1"}


def test_scenario_only_supports_a_root_array():
    schema = {
        "type": "array",
        "minItems": 1,
        "maxItems": 1,
        "items": _obj(x={"type": "string"}, y={"type": "string"}),
    }
    gen = JSONSchemaGenerator(Schema(data=schema))
    out = gen.generate(
        Scenario(name="s", scenario_only=True, overrides={"[0].y": "Y"})
    )
    assert out == [{"y": "Y"}]


def test_default_data_container_is_not_replaced():
    schema = _obj(
        meta={"type": "object", "properties": {"a": {"type": "integer"}}},
        tags={"type": "array", "maxItems": 3, "items": {"type": "string"}},
    )
    gen = JSONSchemaGenerator(Schema(data=schema))
    out = gen.generate(
        Scenario(name="d", default_data={"meta": {"a": 5}, "tags": ["x"]})
    )
    assert out["meta"]["a"] == 5
    assert out["tags"][0] == "x"


# ---------------------------------------------------------------------------
# Nested arrays, root arrays, dotted property names (issue 2)
# ---------------------------------------------------------------------------
def test_array_of_arrays():
    schema = _obj(
        points={
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "number"},
            },
        }
    )
    for out in _generate_many(schema):
        assert all(len(point) == 2 for point in out["points"])


def test_root_array():
    schema = {"type": "array", "minItems": 1, "items": {"type": "string"}}
    for out in _generate_many(schema):
        assert isinstance(out, list) and out
        assert all(isinstance(item, str) for item in out)


def test_root_array_of_objects_with_override():
    schema = {
        "type": "array",
        "minItems": 2,
        "maxItems": 2,
        "items": _obj(id={"type": "integer"}),
    }
    gen = JSONSchemaGenerator(Schema(data=schema))
    out = gen.generate(Scenario(name="s", overrides={"[1].id": 42}))
    assert isinstance(out, list) and len(out) == 2
    assert out[1]["id"] == 42
    assert isinstance(out[0]["id"], int)


def test_property_name_with_dot():
    schema = _obj(**{"a.b": {"type": "string"}})
    for out in _generate_many(schema):
        assert set(out) == {"a.b"}


def test_override_targets_quoted_key_and_nested_index():
    schema = _obj(
        **{
            "a.b": _obj(c={"type": "string"}),
            "points": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number"},
                },
            },
        }
    )
    seen = []

    def record(ctx):
        seen.append(ctx.prop_path)
        return "X"

    scenario = Scenario(
        name="s",
        overrides={'["a.b"].c': record, "points[0][1]": 9.5},
    )
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out["a.b"] == {"c": "X"}
    assert out["points"][0][1] == 9.5
    assert seen == ['["a.b"].c']


# ---------------------------------------------------------------------------
# ctx.data is a live view; forward references are deferred
# ---------------------------------------------------------------------------
def test_context_data_is_the_live_result_for_root_array_items():
    schema = {
        "type": "array",
        "minItems": 2,
        "maxItems": 2,
        "items": _obj(id={"type": "integer"}),
    }
    scenario = Scenario(
        name="s",
        overrides={"[0].id": 1, "[1].id": lambda ctx: ctx.data[0]["id"] + 1},
    )
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out == [{"id": 1}, {"id": 2}]


def test_forward_reference_into_a_later_array_item_is_deferred():
    schema = _obj(
        items={
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": _obj(
                price={"type": "integer", "minimum": 1},
                total={"type": "integer"},
            ),
        }
    )
    scenario = Scenario(
        name="f",
        overrides={
            "items[0].total": lambda ctx: ctx.data["items"][1]["price"]
        },
    )
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out["items"][0]["total"] == out["items"][1]["price"]


def test_forward_reference_to_a_later_sibling_is_deferred():
    schema = _obj(a={"type": "integer"}, b={"type": "integer", "minimum": 1})
    scenario = Scenario(name="f", overrides={"a": lambda ctx: ctx.data["b"]})
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out["a"] == out["b"]


# ---------------------------------------------------------------------------
# uniqueItems (issue 7)
# ---------------------------------------------------------------------------
def test_unique_items_with_enum():
    schema = _obj(
        colors={
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"type": "string", "enum": ["red", "blue", "green"]},
        }
    )
    for out in _generate_many(schema, n=50):
        assert len(set(out["colors"])) == 2


def test_unique_items_enum_is_sampled_without_replacement():
    letters = list("abcdefghij")
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 10,
            "maxItems": 10,
            "uniqueItems": True,
            "items": {"type": "string", "enum": letters},
        }
    )
    for out in _generate_many(schema, n=30):
        assert sorted(out["xs"]) == letters


def test_unique_items_distinguishes_booleans_from_numbers():
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"enum": [0, 1, True, False]},
        }
    )
    for out in _generate_many(schema, n=30):
        keys = {(type(v), v) for v in out["xs"]}
        assert len(keys) == 4, out


def test_unique_items_with_open_domain():
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"type": "integer", "minimum": 0, "maximum": 3},
        }
    )
    for out in _generate_many(schema, n=30):
        assert sorted(out["xs"]) == [0, 1, 2, 3]


def test_unique_items_with_objects():
    schema = _obj(
        items={
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "uniqueItems": True,
            "items": _obj(k={"type": "integer", "minimum": 0, "maximum": 3}),
        }
    )
    for out in _generate_many(schema):
        assert len({item["k"] for item in out["items"]}) == 3


def test_unique_items_unsatisfiable_raises():
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "uniqueItems": True,
            "items": {"type": "string", "enum": ["a", "b"]},
        }
    )
    with pytest.raises(ValueError, match="uniqueItems"):
        JSONSchemaGenerator(Schema(data=schema)).generate()


def test_unique_items_leaves_overridden_items_alone():
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"type": "string", "enum": ["a", "b"]},
        }
    )
    scenario = Scenario(name="o", overrides={"xs[0]": "a", "xs[1]": "a"})
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out["xs"] == ["a", "a"]


# ---------------------------------------------------------------------------
# Recursion ends through the cycle rule; max_depth is a hard cap (issue 8)
# ---------------------------------------------------------------------------
NAMES = [f"level{i}" for i in range(1, 8)] + ["leaf"]


def _required_chain(names):
    node = {"type": "string"}
    for name in reversed(names):
        node = {
            "type": "object",
            "properties": {name: node},
            "required": [name],
        }
    return node


def test_required_chain_of_eight_levels_is_generated_by_default():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _generate_many(_required_chain(NAMES), n=5)


def test_optional_recursion_terminates_silently():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "children": {"type": "array", "items": {"$ref": "#"}},
        },
        "required": ["name"],
    }
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri="file://rec.json"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = gen.generate()

    def depth(node):
        return 1 + max((depth(c) for c in node.get("children", [])), default=0)

    assert "name" in out
    assert depth(out) <= 3


def test_branching_optional_recursion_is_cheap():
    schema = {
        "type": "object",
        "properties": {
            "left": {"$ref": "#"},
            "right": {"$ref": "#"},
            "v": {"type": "integer"},
        },
        "required": ["v"],
    }
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri="file://rec.json"))
    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = gen.generate()
    assert time.perf_counter() - started < 2
    # the first occurrence of "#" below the root is generated in full; at
    # the second occurrence the optional recursion is pruned
    assert set(out["left"]) == {"left", "right", "v"}
    assert out["left"]["left"] == {"v": out["left"]["left"]["v"]}


def test_required_recursion_hits_the_cap_and_warns():
    schema = {
        "type": "object",
        "properties": {"child": {"$ref": "#"}},
        "required": ["child"],
    }
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri="file://rec.json"))
    with pytest.warns(UserWarning, match="max_depth=50"):
        out = gen.generate()
    levels, node = 0, out
    while "child" in node:
        node, levels = node["child"], levels + 1
    assert levels >= 50


def test_hard_cap_can_be_lowered_and_warns_once():
    gen = JSONSchemaGenerator(Schema(data=_required_chain(NAMES)), max_depth=3)
    with pytest.warns(UserWarning, match="max_depth=3") as record:
        out = gen.generate()
    assert len([w for w in record if "max_depth" in str(w.message)]) == 1
    node = out
    for name in NAMES[:4]:
        node = node[name]
    assert node == {}


def test_depth_cut_on_optional_property_is_silent():
    schema = {
        "type": "object",
        "properties": {"child": {"$ref": "#"}, "name": {"type": "string"}},
    }
    gen = JSONSchemaGenerator(
        Schema(data=schema, base_uri="file://rec.json"), max_depth=2
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        gen.generate()


def test_depth_counts_property_levels_not_array_indices():
    node = {"type": "string"}
    for name in reversed(["a", "b", "c", "d", "e", "f", "g"]):
        node = _obj(
            **{
                name: {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": node,
                }
            }
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _generate_many(node, n=5, max_depth=6)
