from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_simple_value_overrides():
    """Test that simple value overrides work correctly."""
    # Create a simple schema
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "is_active": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "address": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "zip": {"type": "string"},
                },
            },
            "optional_field": {"type": "string"},
        },
    }
    schema = Schema(data=schema_data)

    # Create a scenario with simple value overrides (no lambdas)
    scenario = Scenario(
        name="simple_override_scenario",
        overrides={
            "name": "John Smith",  # Simple string
            "age": 42,  # Simple integer
            "is_active": True,  # Simple boolean
            "tags": ["test", "sample"],  # List
            "address.city": "New York",  # Nested simple string
            "address.zip": "10001",  # Nested simple string
            "optional_field": None,  # None value
        },
    )

    # Create the generator
    generator = JSONSchemaGenerator(schema=schema)

    # Generate the data
    result = generator.generate(scenario)

    # Verify the results
    assert result["name"] == "John Smith"
    assert result["age"] == 42
    assert result["is_active"] is True
    assert result["tags"] == ["test", "sample"]
    assert result["address"]["city"] == "New York"
    assert result["address"]["zip"] == "10001"
    assert (
        result["optional_field"] is None
    )  # Verify None value is correctly applied


def test_mixed_overrides():
    """Test that a mix of simple values and lambda functions work correctly."""
    # Create a simple schema
    schema_data = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "created_at": {"type": "string"},
        },
    }
    schema = Schema(data=schema_data)

    # Create a scenario with mixed overrides
    scenario = Scenario(
        name="mixed_override_scenario",
        overrides={
            "id": "user-123",  # Simple value
            "name": lambda ctx: "User " + ctx.prop_path,  # Lambda
            "created_at": lambda ctx: "2023-01-01",  # Lambda
        },
    )

    # Create the generator
    generator = JSONSchemaGenerator(schema=schema)

    # Generate the data
    result = generator.generate(scenario)

    # Verify the results
    assert result["id"] == "user-123"
    assert "User" in result["name"]
    assert result["created_at"] == "2023-01-01"
