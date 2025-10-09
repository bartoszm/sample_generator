from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema

shared_definitions = {
    "Name": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
    },
    "Age": {
        "type": "object",
        "properties": {
            "age": {"type": "integer"},
        },
    },
}


def test_allof_simple() -> None:
    # Simple allOf of two schemas
    schema_data = {
        "definitions": {
            **shared_definitions,
            "Person": {
                "allOf": [
                    {"$ref": "#/definitions/Name"},
                    {"$ref": "#/definitions/Age"},
                ]
            },
        },
        "type": "object",
        "properties": {
            "person": {"$ref": "#/definitions/Person"},
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    scenario = Scenario(
        name="capture_allof_paths",
        overrides={
            "person.name": "Bob",
            "person.age": 25,
        },
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert result == {"person": {"name": "Bob", "age": 25}}


def test_allof_with_inline_definition() -> None:
    # One entry in allOf is an inline schema, the other is a $ref
    schema_data = {
        "definitions": {
            **shared_definitions,
            "Person": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                        },
                    },
                    {"$ref": "#/definitions/Age"},
                ]
            },
        },
        "type": "object",
        "properties": {
            "person": {"$ref": "#/definitions/Person"},
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    scenario = Scenario(
        name="allof_inline",
        overrides={
            "person.name": "Alice",
            "person.age": 30,
        },
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert result == {"person": {"name": "Alice", "age": 30}}


def test_allof_with_inline2_definition() -> None:
    # One entry in allOf is an inline schema, the other is a $ref
    schema_data = {
        "definitions": {
            **shared_definitions,
            "Person": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "allOf": [
                    {"$ref": "#/definitions/Age"},
                ],
            },
        },
        "type": "object",
        "properties": {
            "person": {"$ref": "#/definitions/Person"},
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    scenario = Scenario(
        name="allof_inline",
        overrides={
            "person.name": "Alice",
            "person.age": 30,
        },
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert result == {"person": {"name": "Alice", "age": 30}}


def test_embedded_allof() -> None:
    # allOf embedded directly inside a property (name and age are separate
    # schemas defined locally under the property and referenced via $ref)
    schema_data = {
        "type": "object",
        "definitions": {
            **shared_definitions,
        },
        "properties": {
            "person": {
                "allOf": [
                    {"$ref": "#/definitions/Name"},
                    {"$ref": "#/definitions/Age"},
                    {
                        "type": "object",
                        "properties": {"address": {"type": "string"}},
                    },
                ],
            },
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    scenario = Scenario(
        name="embedded_allof",
        overrides={
            "person.name": "Charlie",
            "person.age": 45,
            "person.address": "123 Main St",
        },
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert result == {
        "person": {"name": "Charlie", "age": 45, "address": "123 Main St"}
    }
