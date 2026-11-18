"""A oneOf branch that only wraps a reference in ``allOf`` is named like
the reference itself (OpenAPI 3.0 puts a ``description`` next to a
``$ref`` that way)."""

from __future__ import annotations

import random

from faker import Faker

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.models import Scenario, Schema

DOG = {
    "type": "object",
    "properties": {"bark": {"type": "boolean"}},
    "required": ["bark"],
}
CAT = {
    "type": "object",
    "properties": {"meow": {"type": "boolean"}},
    "required": ["meow"],
}


def _pet(branches, mapping=None):
    disc = {"propertyName": "petType"}
    if mapping is not None:
        disc["mapping"] = mapping
    return {
        "definitions": {"Dog": DOG, "Cat": CAT},
        "type": "object",
        "properties": {"petType": {"type": "string"}},
        "required": ["petType"],
        "discriminator": disc,
        "oneOf": branches,
    }


def _generate(schema, scenario=None, n=30):
    gen = JSONSchemaGenerator(Schema(data=schema, base_uri="file://pets.json"))
    out = []
    for seed in range(n):
        random.seed(seed)
        Faker.seed(seed)
        out.append(gen.generate(scenario))
    return out


def _expected(sample):
    return "dog" if "bark" in sample else "cat"


WRAPPED = [
    {"allOf": [{"$ref": "#/definitions/Dog"}], "description": "a dog"},
    {"allOf": [{"$ref": "#/definitions/Cat"}]},
]


def test_wrapped_ref_is_named_by_the_implicit_mapping():
    schema = _pet(WRAPPED)
    names = {
        s["petType"]: _expected(s) for s in _generate(schema)
    }  # petType -> kind
    assert names == {"Dog": "dog", "Cat": "cat"}


def test_wrapped_ref_is_named_by_its_mapping_key():
    schema = _pet(
        WRAPPED,
        mapping={"dog": "#/definitions/Dog", "cat": "#/definitions/Cat"},
    )
    for sample in _generate(schema):
        assert sample["petType"] == _expected(sample)


def test_str_selector_finds_a_wrapped_branch():
    schema = _pet(
        WRAPPED,
        mapping={"dog": "#/definitions/Dog", "cat": "#/definitions/Cat"},
    )
    scenario = Scenario(
        name="s", oneof_selectors={"": lambda ctx, cands: "cat"}
    )
    for sample in _generate(schema, scenario, n=10):
        assert sample["petType"] == "cat"
        assert "meow" in sample


def test_a_wrapper_with_constraints_of_its_own_is_not_named():
    """``allOf`` with a second schema is a schema of its own, not the
    reference: it has no name to give."""
    branches = [
        {
            "allOf": [{"$ref": "#/definitions/Dog"}],
            "properties": {"extra": {"type": "string"}},
        },
        {"$ref": "#/definitions/Cat"},
    ]
    for sample in _generate(_pet(branches)):
        if "bark" in sample:
            assert sample["petType"] not in ("Dog", "dog")
        else:
            assert sample["petType"] == "Cat"


def test_a_wrapper_around_several_schemas_is_not_unwrapped():
    branches = [
        {"allOf": [{"$ref": "#/definitions/Dog"}, {"type": "object"}]},
        {"$ref": "#/definitions/Cat"},
    ]
    for sample in _generate(_pet(branches)):
        if "bark" in sample:
            assert sample["petType"] not in ("Dog", "dog")
