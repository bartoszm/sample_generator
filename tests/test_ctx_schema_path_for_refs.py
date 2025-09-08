from __future__ import annotations

from typing import List, Tuple

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_ctx_schema_path_set_for_refs() -> None:
    # Arrange: schema with multiple $refs and nested $ref
    schema_data = {
        "definitions": {
            "Address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "zip": {"type": "string"},
                },
            },
            "Person": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                    "address": {"$ref": "#/definitions/Address"},
                },
            },
        },
        "type": "object",
        "properties": {
            "person1": {"$ref": "#/definitions/Person"},
            "person2": {"$ref": "#/definitions/Person"},
            "addressDirect": {"$ref": "#/definitions/Address"},
        },
    }

    # Use a deterministic base_uri so schema_path includes this (jsonref may retain it)
    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    events: List[Tuple[str, str | None]] = []

    def capture(path: str, ret_val):
        def _fn(ctx):
            # record (prop_path, schema_path)
            events.append((ctx.prop_path, ctx.schema_path))
            return ret_val

        return _fn

    scenario = Scenario(
        name="capture_schema_paths",
        overrides={
            # person1 leaf fields (Person -> Address nested)
            "person1.name": capture("person1.name", "Alice"),
            "person1.age": capture("person1.age", 30),
            "person1.address.street": capture(
                "person1.address.street", "Main St"
            ),
            "person1.address.zip": capture("person1.address.zip", "00000"),
            # person2 leaf fields
            "person2.name": capture("person2.name", "Bob"),
            "person2.age": capture("person2.age", 40),
            "person2.address.street": capture(
                "person2.address.street", "Second St"
            ),
            "person2.address.zip": capture("person2.address.zip", "11111"),
            # direct address ref leaf fields
            "addressDirect.street": capture(
                "addressDirect.street", "Direct Ave"
            ),
            "addressDirect.zip": capture("addressDirect.zip", "22222"),
        },
    ).normalize()

    gen = JSONSchemaGenerator(schema)

    # Act
    result = gen.generate(scenario)

    # Sanity: result is shaped as expected (values come from overrides)
    assert result["person1"]["name"] == "Alice"
    assert result["person1"]["age"] == 30
    assert result["person1"]["address"]["street"] == "Main St"
    assert result["person1"]["address"]["zip"] == "00000"

    assert result["person2"]["name"] == "Bob"
    assert result["person2"]["age"] == 40
    assert result["person2"]["address"]["street"] == "Second St"
    assert result["person2"]["address"]["zip"] == "11111"

    assert result["addressDirect"]["street"] == "Direct Ave"
    assert result["addressDirect"]["zip"] == "22222"

    # Assert: for every override under a $ref, ctx.schema_path matches the ref target
    # Gather expectations
    def endswith_fragment(sp: str | None, frag: str) -> bool:
        return sp is not None and sp.endswith(frag)

    for path, sp in events:
        if path.startswith("person1.address") or path.startswith(
            "person2.address"
        ):
            assert endswith_fragment(
                sp, "#/definitions/Address"
            ), f"schema_path for {path} should point to Address, got {sp}"
        elif path.startswith("person1.") or path.startswith("person2."):
            assert endswith_fragment(
                sp, "#/definitions/Person"
            ), f"schema_path for {path} should point to Person, got {sp}"
        elif path.startswith("addressDirect."):
            assert endswith_fragment(
                sp, "#/definitions/Address"
            ), f"schema_path for {path} should point to Address, got {sp}"
        else:
            raise AssertionError(f"Unexpected path captured: {path}")
