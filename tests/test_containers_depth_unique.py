"""Result assembly: empty containers are emitted, nested and root arrays
and dotted property names work, ``uniqueItems`` is honoured, and a
``max_depth`` cut of a required property warns."""

from __future__ import annotations

import random
import warnings

import pytest
from faker import Faker
from jsonschema import Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.models import Scenario, Schema


def _obj(**props):
    return {"type": "object", "properties": props, "required": list(props)}


def _generate_many(schema, n=30, scenario=None, **generator_kwargs):
    """Generate *n* seeded samples, assert each validates, return them."""
    gen = JSONSchemaGenerator(Schema(data=schema), **generator_kwargs)
    validator = Draft7Validator(
        schema, format_checker=Draft7Validator.FORMAT_CHECKER
    )
    outputs = []
    for seed in range(n):
        random.seed(seed)
        Faker.seed(seed)
        out = gen.generate(scenario)
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


def test_unique_items_unsatisfiable_warns():
    schema = _obj(
        xs={
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"type": "string", "const": "same"},
        }
    )
    gen = JSONSchemaGenerator(Schema(data=schema))
    with pytest.warns(UserWarning, match="uniqueItems"):
        out = gen.generate()
    assert out["xs"] == ["same", "same"]


# ---------------------------------------------------------------------------
# max_depth (issue 8)
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


def test_depth_cut_on_required_property_warns_once():
    gen = JSONSchemaGenerator(Schema(data=_required_chain(NAMES)))
    with pytest.warns(UserWarning, match="max_depth=6") as record:
        out = gen.generate()
    assert len([w for w in record if "max_depth" in str(w.message)]) == 1
    node = out
    for name in NAMES[:7]:
        node = node[name]
    assert node == {}, "containers above the cut are present, the leaf is not"


def test_depth_cut_on_optional_property_is_silent():
    schema = {
        "type": "object",
        "properties": {"child": {"$ref": "#"}, "name": {"type": "string"}},
    }
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri="file://rec.json"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        gen.generate()


def test_depth_can_be_raised():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _generate_many(_required_chain(NAMES), n=5, max_depth=20)


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
        _generate_many(node, n=5)
