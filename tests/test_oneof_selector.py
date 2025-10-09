from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_oneof_selector_index():
    schema_data = {
        "type": "object",
        "properties": {
            "pet": {
                "oneOf": [
                    {"type": "string", "const": "dog"},
                    {"type": "string", "const": "cat"},
                    {"type": "string", "const": "bird"},
                ]
            }
        },
    }
    schema = Schema(data=schema_data)

    # Selector returns index 1 -> "cat"
    def select_cat(ctx, schemas):
        return 1

    scenario = Scenario(
        name="oneof_index", oneof_selectors={"pet": select_cat}
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert result["pet"] == "cat"


def test_oneof_selector_schema():
    schema_data = {
        "type": "object",
        "properties": {
            "pet": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"kind": {"const": "dog"}},
                    },
                    {
                        "type": "object",
                        "properties": {"kind": {"const": "cat"}},
                    },
                ]
            }
        },
    }
    schema = Schema(data=schema_data)

    # Selector returns a schema directly
    def select_dog_schema(ctx, schemas):
        return schemas[0]

    scenario = Scenario(
        name="oneof_schema", oneof_selectors={"pet": select_dog_schema}
    )

    gen = JSONSchemaGenerator(schema=schema)
    result = gen.generate(scenario)

    assert isinstance(result["pet"], dict)
    assert result["pet"].get("kind") == "dog"
