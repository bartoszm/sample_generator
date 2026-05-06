from __future__ import annotations

import warnings

import pytest

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema


def test_from_oas_resolves_cross_component_refs() -> None:
    """Test that from_oas correctly resolves $refs to other components."""
    oas_dict = {
        "components": {
            "schemas": {
                "Category": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
                "Pet": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"$ref": "#/components/schemas/Category"},
                    },
                    "required": ["name", "category"],
                },
            }
        }
    }

    schema = Schema.from_oas(oas_dict, name="Pet")
    gen = JSONSchemaGenerator(schema)
    result = gen.generate()

    assert "name" in result
    assert "category" in result
    assert "id" in result["category"]
    assert "name" in result["category"]


def test_from_oas_resolves_allof_refs() -> None:
    """Test that from_oas works with allOf inheritance across components."""
    oas_dict = {
        "components": {
            "schemas": {
                "Animal": {
                    "type": "object",
                    "properties": {
                        "species": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                    "required": ["species"],
                },
                "Dog": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Animal"},
                        {
                            "type": "object",
                            "properties": {
                                "breed": {"type": "string"},
                            },
                        },
                    ]
                },
            }
        }
    }

    schema = Schema.from_oas(oas_dict, name="Dog")
    gen = JSONSchemaGenerator(schema)
    result = gen.generate()

    assert "species" in result
    assert "age" in result
    assert "breed" in result


def test_from_oas_raises_on_missing_name() -> None:
    """Test that from_oas raises ValueError for non-existent component."""
    oas_dict = {
        "components": {
            "schemas": {
                "Existing": {"type": "object"},
            }
        }
    }

    with pytest.raises(ValueError, match="NonExistent.*not found"):
        Schema.from_oas(oas_dict, name="NonExistent")


def test_from_oas_custom_base_uri() -> None:
    """Test that from_oas accepts and uses a custom base_uri."""
    oas_dict = {
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                }
            }
        }
    }

    schema = Schema.from_oas(
        oas_dict, name="Item", base_uri="file:///schemas/my.yaml"
    )

    assert (
        schema.base_uri == "file:///schemas/my.yaml#/components/schemas/Item"
    )


def test_from_raw_data_warns_on_oas_without_fragment() -> None:
    """Test warning when from_raw_data receives OAS dict without fragment."""
    oas_dict = {
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                }
            }
        }
    }

    with pytest.warns(UserWarning, match="components.*from_oas"):
        Schema.from_raw_data(oas_dict, base_uri="file:///oas.yaml")


def test_from_raw_data_no_warn_with_fragment() -> None:
    """Test no warning when base_uri has fragment."""
    oas_dict = {
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                }
            }
        }
    }

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            Schema.from_raw_data(
                oas_dict, base_uri="file:///oas.yaml#/components/schemas/User"
            )
        except UserWarning:
            pytest.fail("Unexpected warning when fragment is in base_uri")


def test_from_raw_data_no_warn_without_components() -> None:
    """Test no warning for plain JSON Schema (no components key)."""
    schema_dict = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
    }

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            Schema.from_raw_data(schema_dict, base_uri="file:///schema.json")
        except UserWarning:
            pytest.fail("Unexpected warning for schema without components key")


def test_from_oas_nested_allof_refs() -> None:
    """
    Test from_oas with deeply nested allOf refs (inheritance chain).
    """
    oas_dict = {
        "components": {
            "schemas": {
                "Base": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                    },
                },
                "Extended": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Base"},
                        {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                            },
                        },
                    ]
                },
                "Final": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Extended"},
                        {
                            "type": "object",
                            "properties": {
                                "extra": {"type": "boolean"},
                            },
                        },
                    ]
                },
            }
        }
    }

    schema = Schema.from_oas(oas_dict, name="Final")
    gen = JSONSchemaGenerator(schema)
    result = gen.generate()

    assert "id" in result
    assert "name" in result
    assert "extra" in result


def test_from_oas_array_items_ref() -> None:
    """Test from_oas with array items referencing another component."""
    oas_dict = {
        "components": {
            "schemas": {
                "Tag": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "label": {"type": "string"},
                    },
                },
                "Item": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"$ref": "#/components/schemas/Tag"},
                        },
                    },
                    "required": ["name", "tags"],
                },
            }
        }
    }

    schema = Schema.from_oas(oas_dict, name="Item")
    gen = JSONSchemaGenerator(schema)
    result = gen.generate()

    assert "name" in result
    assert "tags" in result
    assert isinstance(result["tags"], list)
    assert len(result["tags"]) >= 1
    tag = result["tags"][0]
    assert "id" in tag
    assert "label" in tag
