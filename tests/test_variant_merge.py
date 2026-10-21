"""oneOf/anyOf: the chosen branch is generated together with the keywords
next to it, and for oneOf the properties that only other branches require
are left out."""

from __future__ import annotations

import random

from faker import Faker
from jsonschema import Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.models import Scenario, Schema


def _generate_many(schema, n=30, scenario=None, base_uri=None):
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri=base_uri))
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


NAME_OR_CODE = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "code": {"type": "integer"}},
    "oneOf": [{"required": ["name"]}, {"required": ["code"]}],
}


def test_nested_oneof_with_required_only_branches():
    schema = {
        "type": "object",
        "properties": {"key": NAME_OR_CODE},
        "required": ["key"],
    }
    outputs = _generate_many(schema)
    keys = {frozenset(out["key"]) for out in outputs}
    assert keys == {frozenset({"name"}), frozenset({"code"})}


def test_root_oneof_with_required_only_branches():
    outputs = _generate_many(NAME_OR_CODE)
    assert {frozenset(out) for out in outputs} == {
        frozenset({"name"}),
        frozenset({"code"}),
    }


def test_oneof_with_format_only_branches():
    schema = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "oneOf": [{"format": "ipv4"}, {"format": "ipv6"}],
            }
        },
        "required": ["host"],
    }
    outputs = _generate_many(schema)
    assert {":" in out["host"] for out in outputs} == {True, False}


def test_typed_branch_keeps_parent_properties_and_required():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "code": {"type": "integer"},
        },
        "required": ["name"],
        "oneOf": [{"type": "object", "required": ["code"]}],
    }
    for out in _generate_many(schema):
        assert set(out) == {"name", "code"}


def test_anyof_with_required_only_branches():
    schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "code": {"type": "integer"},
                },
                "anyOf": [{"required": ["name"]}, {"required": ["code"]}],
            }
        },
        "required": ["key"],
    }
    for out in _generate_many(schema):
        assert set(out["key"]) & {"name", "code"}


def test_selector_still_applies_after_merge():
    schema = {
        "type": "object",
        "properties": {"key": NAME_OR_CODE},
        "required": ["key"],
    }
    scenario = Scenario(name="s", oneof_selectors={"key": 1})
    for out in _generate_many(schema, scenario=scenario):
        assert set(out["key"]) == {"code"}


def test_override_keeps_property_required_by_other_branch():
    schema = {
        "type": "object",
        "properties": {"key": NAME_OR_CODE},
        "required": ["key"],
    }
    scenario = Scenario(
        name="s", oneof_selectors={"key": 0}, overrides={"key.code": 7}
    )
    out = JSONSchemaGenerator(Schema(data=schema)).generate(scenario)
    assert out["key"]["code"] == 7
    assert isinstance(out["key"]["name"], str)


def test_minimal_mode_generates_required_of_chosen_branch_only():
    schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "code": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "oneOf": [{"required": ["name"]}, {"required": ["code"]}],
            }
        },
        "required": ["key"],
    }
    scenario = Scenario(
        name="m", minimal_mode=True, oneof_selectors={"key": 1}
    )
    for out in _generate_many(schema, scenario=scenario):
        assert out["key"] == {"code": out["key"]["code"]}


def test_allof_next_to_oneof():
    schema = {
        "type": "object",
        "allOf": [
            {
                "properties": {"base": {"type": "string"}},
                "required": ["base"],
            }
        ],
        "properties": {
            "name": {"type": "string"},
            "code": {"type": "integer"},
        },
        "oneOf": [{"required": ["name"]}, {"required": ["code"]}],
    }
    for out in _generate_many(schema):
        assert "base" in out
        assert len({"name", "code"} & set(out)) == 1


REF_SCHEMA = {
    "definitions": {
        "Card": {
            "type": "object",
            "properties": {"last4": {"type": "string"}},
            "required": ["last4"],
        },
        "Bank": {
            "type": "object",
            "properties": {"iban": {"type": "string"}},
            "required": ["iban"],
        },
    },
    "type": "object",
    "properties": {
        "method": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "oneOf": [
                {"$ref": "#/definitions/Card"},
                {"$ref": "#/definitions/Bank"},
            ],
        }
    },
    "required": ["method"],
}


def test_ref_branch_merged_with_parent_keeps_schema_path():
    seen = []

    def capture(ctx):
        seen.append(ctx.schema_path)
        return "1234"

    scenario = Scenario(
        name="s",
        oneof_selectors={"method": 0},
        overrides={"method.last4": capture},
    )
    outputs = _generate_many(
        REF_SCHEMA, n=5, scenario=scenario, base_uri="file://dummy.json"
    )
    for out in outputs:
        assert set(out["method"]) == {"id", "last4"}
    assert seen and all(p.endswith("#/definitions/Card") for p in seen)


def test_ref_branch_without_sibling_keywords_is_unchanged():
    schema = {
        "definitions": REF_SCHEMA["definitions"],
        "type": "object",
        "properties": {
            "method": {
                "discriminator": {"propertyName": "kind"},
                "oneOf": [
                    {"$ref": "#/definitions/Card"},
                    {"$ref": "#/definitions/Bank"},
                ],
            }
        },
        "required": ["method"],
    }
    seen = []

    def capture(ctx):
        seen.append(ctx.schema_path)
        return "DE00"

    scenario = Scenario(
        name="s",
        oneof_selectors={"method": 1},
        overrides={"method.iban": capture},
    )
    outputs = _generate_many(
        schema, n=5, scenario=scenario, base_uri="file://dummy.json"
    )
    for out in outputs:
        assert out["method"] == {"iban": "DE00"}
    assert seen and all(p.endswith("#/definitions/Bank") for p in seen)
