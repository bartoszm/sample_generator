"""A oneOf branch that only wraps a reference in ``allOf`` is named like
the reference itself (OpenAPI 3.0 puts a ``description`` next to a
``$ref`` that way)."""

from __future__ import annotations

import json
import random

import pytest
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


# -- a wrapper that is a named schema itself, and ``nullable`` ---------------


def _oas(branch_for_dog, mapping=None):
    disc = {"propertyName": "kind"}
    if mapping:
        disc["mapping"] = mapping
    return {
        "openapi": "3.0.3",
        "components": {
            "schemas": {
                "Dog": {
                    "type": "object",
                    "properties": {"bark": {"type": "boolean"}},
                    "required": ["bark"],
                },
                "Cat": {
                    "type": "object",
                    "properties": {"meow": {"type": "boolean"}},
                    "required": ["meow"],
                },
                "Wrapper": {
                    "description": "a dog, by another name",
                    "allOf": [{"$ref": "#/components/schemas/Dog"}],
                },
                "Root": {
                    "type": "object",
                    "properties": {"kind": {"type": "string"}},
                    "required": ["kind"],
                    "discriminator": disc,
                    "oneOf": [
                        branch_for_dog,
                        {"$ref": "#/components/schemas/Cat"},
                    ],
                },
            }
        },
    }


def _loaded(loader, doc, tmp_path):
    path = tmp_path / "oas.json"
    path.write_text(json.dumps(doc))
    uri = path.as_uri()
    if loader == "from_oas":
        return Schema.from_oas(doc, "Root", base_uri=uri)
    if loader == "from_raw_data":
        return Schema.from_raw_data(
            json.loads(path.read_text()), uri + "#/components/schemas/Root"
        )
    # the root schema with the document's components next to it, so the
    # references resolve against the schema itself
    root = {
        **doc["components"]["schemas"]["Root"],
        "components": doc["components"],
    }
    return Schema(data=root, base_uri=uri)


def _kinds(schema):
    gen = JSONSchemaGenerator(schema)
    kinds = set()
    for seed in range(30):
        random.seed(seed)
        Faker.seed(seed)
        kinds.add(gen.generate()["kind"])
    return kinds


LOADERS = ["from_oas", "from_raw_data", "plain"]


@pytest.mark.parametrize("loader", LOADERS)
def test_a_named_wrapper_is_named_after_itself(loader, tmp_path):
    doc = _oas({"$ref": "#/components/schemas/Wrapper"})
    assert _kinds(_loaded(loader, doc, tmp_path)) == {"Wrapper", "Cat"}


@pytest.mark.parametrize("loader", LOADERS)
def test_a_named_wrapper_keeps_its_mapping_key(loader, tmp_path):
    doc = _oas(
        {"$ref": "#/components/schemas/Wrapper"},
        mapping={"w": "#/components/schemas/Wrapper"},
    )
    assert _kinds(_loaded(loader, doc, tmp_path)) == {"w", "Cat"}


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("keyword", ["nullable", "readOnly", "default"])
def test_annotations_next_to_the_wrapped_ref_do_not_hide_it(
    loader, keyword, tmp_path
):
    """``allOf`` + ``nullable`` is how OpenAPI 3.0 makes a ``$ref``
    nullable."""
    value = False if keyword == "default" else True
    branch = {"allOf": [{"$ref": "#/components/schemas/Dog"}]}
    branch[keyword] = value
    assert _kinds(_loaded(loader, _oas(branch), tmp_path)) == {"Dog", "Cat"}
