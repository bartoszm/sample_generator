from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema


def test_oas_components_allof_inheritance_coverage() -> None:
    # OpenAPI-like structure using components/schemas
    schema_data = {
        "components": {
            "schemas": {
                "Grampma": {
                    "type": "object",
                    "properties": {
                        "g_name": {"type": "string"},
                        "g_id": {"type": "integer"},
                    },
                },
                "Root": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Grampma"},
                        {
                            "type": "object",
                            "properties": {
                                "r_flag": {"type": "boolean"},
                                "r_count": {"type": "integer"},
                            },
                        },
                    ]
                },
                "Subcomponent": {
                    "type": "object",
                    "properties": {
                        "s_name": {"type": "string"},
                    },
                },
                "Child": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Root"},
                        {"$ref": "#/components/schemas/Grampma"},
                        {
                            "type": "object",
                            "properties": {
                                "c_title": {"type": "string"},
                                "subcomponents": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {
                                        "$ref": "#/components/schemas/Subcomponent"
                                    },
                                },
                            },
                        },
                    ]
                },
            }
        },
        "type": "object",
        "properties": {"child": {"$ref": "#/components/schemas/Child"}},
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    gen = JSONSchemaGenerator(schema)

    # Act (no Scenario)
    result = gen.generate()

    # Assert that all Child paths (including inherited from parents) are present
    assert "child" in result
    child = result["child"]

    # Inherited from Grampma
    assert "g_name" in child
    assert "g_id" in child

    # Inherited from Root (and Root inherits Grampma too)
    assert "r_flag" in child
    assert "r_count" in child

    # Child's own properties
    assert "c_title" in child
    assert "subcomponents" in child and isinstance(
        child["subcomponents"], list
    )
    assert len(child["subcomponents"]) >= 1
    first = child["subcomponents"][0]
    assert isinstance(first, dict)
    assert "s_name" in first
