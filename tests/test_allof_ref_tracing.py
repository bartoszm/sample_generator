from __future__ import annotations

from typing import List, Tuple

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_allof_and_ref_schema_path_tracing() -> None:
    # Person is an allOf of Name, Age and an inline schema that includes Address ref
    schema_data = {
        "definitions": {
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
            "Address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "zip": {"type": "string"},
                },
            },
            "Person": {
                "allOf": [
                    {"$ref": "#/definitions/Name"},
                    {"$ref": "#/definitions/Age"},
                    {
                        "type": "object",
                        "properties": {
                            "address": {"$ref": "#/definitions/Address"}
                        },
                    },
                ]
            },
        },
        "type": "object",
        "properties": {
            "person": {"$ref": "#/definitions/Person"},
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    captured: List[Tuple[str, str | None]] = []

    def cap(ret):
        def _fn(ctx):
            captured.append((ctx.prop_path, ctx.schema_path))
            return ret

        return _fn

    scenario = Scenario(
        name="allof_ref_capture",
        overrides={
            "person.name": cap("Alice"),
            "person.age": cap(33),
            "person.address.street": cap("Main"),
            "person.address.zip": cap("00000"),
        },
    ).normalize()

    gen = JSONSchemaGenerator(schema)

    # Act
    result = gen.generate(scenario)

    # Sanity on values
    assert result["person"]["name"] == "Alice"
    assert result["person"]["age"] == 33
    assert result["person"]["address"]["street"] == "Main"
    assert result["person"]["address"]["zip"] == "00000"

    # Assert schema_path tracing: direct children of Person keep Person ref; for nested Address under allOf
    # the schema_path may remain on Person depending on jsonref materialization, but must be set.
    for path, sp in captured:
        assert sp is not None, f"schema_path must be set for {path}"
        if path in ("person.name", "person.age"):
            assert sp.endswith(
                "#/definitions/Person"
            ), f"{path} should derive from Person, got {sp}"
        if path.startswith("person.address."):
            assert sp.endswith(
                "#/definitions/Address"
            ), f"{path} should derive from Address, got {sp}"


def test_allof_with_deep_nested_refs_tracing() -> None:
    # Build a schema where Person is allOf(...) and deeper levels have nested refs and arrays
    schema_data = {
        "definitions": {
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
            "Coordinates": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                },
            },
            "City": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "coordinates": {"$ref": "#/definitions/Coordinates"},
                },
            },
            "Address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"$ref": "#/definitions/City"},
                },
            },
            "Phone": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                },
            },
            "Contacts": {
                "type": "object",
                "properties": {
                    "phones": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/definitions/Phone"},
                    },
                },
            },
            "Person": {
                "allOf": [
                    {"$ref": "#/definitions/Name"},
                    {"$ref": "#/definitions/Age"},
                    {
                        "type": "object",
                        "properties": {
                            "address": {"$ref": "#/definitions/Address"},
                            "contacts": {"$ref": "#/definitions/Contacts"},
                        },
                    },
                ]
            },
        },
        "type": "object",
        "properties": {
            "person": {"$ref": "#/definitions/Person"},
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    captured: List[Tuple[str, str | None]] = []

    def cap(ret):
        def _fn(ctx):
            captured.append((ctx.prop_path, ctx.schema_path))
            return ret

        return _fn

    scenario = Scenario(
        name="deep_allof_ref_capture",
        overrides={
            # Direct children
            "person.name": cap("Carol"),
            "person.age": cap(28),
            # Nested Address -> City -> Coordinates
            "person.address.street": cap("Third"),
            "person.address.city.name": cap("Metropolis"),
            "person.address.city.coordinates.lat": cap(52.1),
            "person.address.city.coordinates.lng": cap(21.0),
            # Contacts with refs and array
            "person.contacts.phones[0].number": cap("+200000000"),
        },
    ).normalize()

    gen = JSONSchemaGenerator(schema)

    # Act
    result = gen.generate(scenario)

    # Sanity on values
    assert result["person"]["name"] == "Carol"
    assert result["person"]["age"] == 28
    assert result["person"]["address"]["street"] == "Third"
    assert result["person"]["address"]["city"]["name"] == "Metropolis"
    assert result["person"]["address"]["city"]["coordinates"]["lat"] == 52.1
    assert result["person"]["address"]["city"]["coordinates"]["lng"] == 21.0
    assert result["person"]["contacts"]["phones"][0]["number"] == "+200000000"

    # Assertions on schema_path tracing for deeper refs
    def ends(sp: str | None, frag: str) -> bool:
        return sp is not None and sp.endswith(frag)

    for path, sp in captured:
        if path in ("person.name", "person.age"):
            assert ends(sp, "#/definitions/Person")
        elif path.startswith("person.address.city.coordinates."):
            assert ends(
                sp, "#/definitions/Coordinates"
            ), f"{path} should derive from Coordinates, got {sp}"
        elif path.startswith("person.address.city."):
            assert ends(
                sp, "#/definitions/City"
            ), f"{path} should derive from City, got {sp}"
        elif path.startswith("person.address."):
            assert ends(
                sp, "#/definitions/Address"
            ), f"{path} should derive from Address, got {sp}"
        elif path.startswith("person.contacts.phones[0]"):
            assert ends(
                sp, "#/definitions/Phone"
            ), f"{path} should derive from Phone (array items), got {sp}"
        elif path.startswith("person.contacts"):
            assert ends(
                sp, "#/definitions/Contacts"
            ), f"{path} should derive from Contacts, got {sp}"
