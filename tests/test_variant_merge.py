"""oneOf/anyOf: the chosen branch is generated together with the keywords
next to it, and for oneOf the properties that only other branches require
are left out."""

from __future__ import annotations

import random
import re

from faker import Faker
from jsonschema import Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.helpers.allof_handler import allof_merge
from json_sample_generator.models import Scenario, Schema


def _generate_many(schema, n=30, scenario=None, base_uri=None, validate=True):
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri=base_uri))
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


# ---------------------------------------------------------------------------
# Review cases: required inside allOf, nested oneOf, refined properties
# ---------------------------------------------------------------------------
def test_pruning_sees_required_nested_in_allof():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "oneOf": [
            {"allOf": [{"required": ["a"]}]},
            {"allOf": [{"required": ["b"]}]},
        ],
    }
    outputs = _generate_many(schema, n=50)
    assert {frozenset(out) for out in outputs} == {
        frozenset({"a"}),
        frozenset({"b"}),
    }


NESTED = {
    "type": "object",
    "properties": {
        "a": {"type": "string"},
        "b": {"type": "string"},
        "c": {"type": "string"},
    },
    "oneOf": [
        {
            "required": ["a"],
            "oneOf": [{"required": ["b"]}, {"required": ["c"]}],
        },
        {"required": ["c"]},
    ],
}


def test_nested_oneof_can_require_a_property_the_outer_oneof_excluded():
    # The outer pass excludes "c" (only the other branch requires it), but
    # its definition stays, so the inner branch that requires "c" can still
    # generate it. Note that {"a", "c"} is inherently non-exclusive in this
    # schema (it also satisfies the outer {"required": ["c"]} branch), so
    # the outcomes are checked structurally rather than with a validator.
    outputs = _generate_many(NESTED, n=50, validate=False)
    assert {frozenset(out) for out in outputs} <= {
        frozenset({"a", "b"}),
        frozenset({"a", "c"}),
        frozenset({"b", "c"}),
    }
    # Force outer branch 0 then inner branch 1: both sites sit at the root
    # path, so one selector serves both and decides by the candidates.
    scenario = Scenario(
        name="s",
        oneof_selectors={
            "": lambda ctx, schemas: 0 if "oneOf" in schemas[0] else 1
        },
    )
    out = JSONSchemaGenerator(Schema(data=NESTED)).generate(scenario)
    assert set(out) == {"a", "c"}


def test_branch_refining_a_parent_property_keeps_its_type():
    schema = {
        "type": "object",
        "properties": {"k": {"type": "string"}},
        "required": ["k"],
        "oneOf": [
            {"properties": {"k": {"pattern": "^a[0-9]$"}}},
            {"properties": {"k": {"pattern": "^b[0-9]$"}}},
        ],
    }
    outputs = _generate_many(schema, n=50)
    assert all(re.fullmatch("[ab][0-9]", out["k"]) for out in outputs)
    assert {out["k"][0] for out in outputs} == {"a", "b"}

    numeric = {
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 100}},
        "required": ["n"],
        "oneOf": [{"properties": {"n": {"maximum": 200}}}],
    }
    for out in _generate_many(numeric, n=30):
        assert 100 <= out["n"] <= 200


def test_allof_keeps_both_definitions_of_a_property():
    merged = allof_merge(
        {
            "allOf": [
                {"properties": {"k": {"type": "string"}}},
                {"properties": {"k": {"pattern": "^a[0-9]$"}}},
            ]
        }
    )
    assert merged["properties"]["k"] == {
        "allOf": [{"type": "string"}, {"pattern": "^a[0-9]$"}]
    }
    schema = {
        "type": "object",
        "required": ["k"],
        "allOf": [
            {"properties": {"k": {"type": "string"}}},
            {"properties": {"k": {"pattern": "^a[0-9]$"}}},
        ],
    }
    for out in _generate_many(schema, n=30):
        assert re.fullmatch("a[0-9]", out["k"])


PET_SCHEMA = {
    "definitions": {
        "Dog": {
            "type": "object",
            "properties": {
                "petType": {"const": "dog"},
                "bark": {"type": "string"},
            },
            "required": ["petType", "bark"],
        },
        "Cat": {
            "type": "object",
            "properties": {
                "petType": {"const": "cat"},
                "meow": {"type": "string"},
            },
            "required": ["petType", "meow"],
        },
    },
    "type": "object",
    "properties": {
        "petType": {"type": "string"},
        "name": {"type": "string"},
    },
    "required": ["name", "petType"],
    "discriminator": {
        "propertyName": "petType",
        "mapping": {"dog": "#/definitions/Dog", "cat": "#/definitions/Cat"},
    },
    "oneOf": [{"$ref": "#/definitions/Dog"}, {"$ref": "#/definitions/Cat"}],
}


def test_openapi_discriminator_shape_with_shared_properties():
    outputs = _generate_many(PET_SCHEMA, n=30, base_uri="file://pets.json")
    assert {out["petType"] for out in outputs} == {"dog", "cat"}
    for out in outputs:
        assert "name" in out
        assert ("bark" in out) != ("meow" in out)


# ---------------------------------------------------------------------------
# Round 2: allOf wrappers and the recursion rule, schema_path, exclusivity
# without parent keywords, array items
# ---------------------------------------------------------------------------
import time  # noqa: E402

from json_sample_generator.break_enum import collect_break_sites  # noqa: E402
from json_sample_generator.scenario_enum import (  # noqa: E402
    collect_variant_sites,
)

REFINED_NODE = {
    "definitions": {
        "Base": {
            "type": "object",
            "required": ["v"],
            "properties": {
                "v": {"type": "string"},
                "next": {"$ref": "#/definitions/Node"},
            },
        },
        "Node": {
            "allOf": [
                {"$ref": "#/definitions/Base"},
                {
                    "properties": {
                        "next": {"$ref": "#/definitions/Node"},
                        "kind": {"oneOf": [{"const": "x"}, {"const": "y"}]},
                    }
                },
            ]
        },
    },
    "type": "object",
    "required": ["root"],
    "properties": {"root": {"$ref": "#/definitions/Node"}},
}


def test_recursive_ref_redeclared_through_allof_stops_early():
    gen = JSONSchemaGenerator(
        Schema(data=REFINED_NODE, base_uri="file://node.json")
    )
    started = time.perf_counter()
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = gen.generate()
    assert time.perf_counter() - started < 1
    # root.next is the first recurrence of Node: required members only,
    # so the optional chain stops there
    assert "v" in out["root"]["next"]
    assert "next" not in out["root"]["next"]
    # the enumerators see the same thing
    resolved = Schema.from_raw_data(REFINED_NODE, "file://node.json")
    started = time.perf_counter()
    assert [s.path for s in collect_variant_sites(resolved)] == ["root.kind"]
    assert len(collect_break_sites(resolved)) < 10
    assert time.perf_counter() - started < 1


def test_redeclared_ref_property_keeps_schema_path():
    schema = {
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        },
        "type": "object",
        "allOf": [
            {"properties": {"pet": {"$ref": "#/definitions/Pet"}}},
            {"properties": {"pet": {"$ref": "#/definitions/Pet"}}},
            {
                "properties": {
                    "other": {
                        "allOf": [
                            {"$ref": "#/definitions/Pet"},
                            {"description": "a refined reference"},
                        ]
                    }
                }
            },
        ],
    }
    seen = {}

    def capture(key):
        def _fn(ctx):
            seen[key] = ctx.schema_path
            return "Rex"

        return _fn

    scenario = Scenario(
        name="s",
        overrides={"pet.name": capture("pet"), "other.name": capture("other")},
    )
    out = JSONSchemaGenerator(
        Schema(data=schema, base_uri="file://pets.json")
    ).generate(scenario)
    assert out["pet"] == {"name": "Rex"} and out["other"] == {"name": "Rex"}
    assert seen["pet"].endswith("#/definitions/Pet")
    assert seen["other"].endswith("#/definitions/Pet")


def test_allof_merge_keeps_a_single_ref_when_redeclared():
    schema = Schema.from_raw_data(
        {
            "definitions": {"Pet": {"type": "object"}},
            "allOf": [
                {"properties": {"pet": {"$ref": "#/definitions/Pet"}}},
                {"properties": {"pet": {"$ref": "#/definitions/Pet"}}},
            ],
        },
        "file://pets.json",
    )
    merged = allof_merge(schema.data)
    assert "allOf" not in merged["properties"]["pet"]


REF_ONLY_ONEOF = {
    "oneOf": [{"$ref": "#/definitions/X"}, {"$ref": "#/definitions/Y"}],
    "definitions": {
        "Base": {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        },
        "X": {"allOf": [{"$ref": "#/definitions/Base"}, {"required": ["a"]}]},
        "Y": {"allOf": [{"$ref": "#/definitions/Base"}, {"required": ["b"]}]},
    },
}


def test_exclusivity_applies_without_parent_keywords():
    outputs = _generate_many(REF_ONLY_ONEOF, n=50, base_uri="file://xy.json")
    assert {frozenset(out) for out in outputs} == {
        frozenset({"a"}),
        frozenset({"b"}),
    }


def test_excluded_properties_do_not_leak_into_array_items():
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"c": {"type": "string"}, "d": {"type": "string"}},
        },
        "oneOf": [{"required": ["c"]}, {"minItems": 1, "maxItems": 1}],
    }
    out = JSONSchemaGenerator(Schema(data=schema)).generate(
        Scenario(name="s", oneof_selectors={"": 1})
    )
    assert len(out) == 1 and set(out[0]) == {"c", "d"}
