import pytest

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Schema


def test_fragment_resolution():
    """Test fragment resolution through the public generate API"""
    schema_data = {
        "definitions": {
            "MySchemaModel": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
            }
        },
        "type": "object",
        "properties": {"model": {"$ref": "#/definitions/MySchemaModel"}},
    }
    schema = Schema(base_uri="file://dummy.json", data=schema_data)
    generator = JSONSchemaGenerator(schema)

    # Test indirectly through the generate API
    result = generator.generate()

    assert "model" in result, "Generated data missing 'model' property"
    assert "name" in result["model"], "Model missing 'name' property"
    assert "age" in result["model"], "Model missing 'age' property"
    assert isinstance(
        result["model"]["name"], str
    ), "Model name should be a string"
    assert isinstance(
        result["model"]["age"], int
    ), "Model age should be an integer"


def test_generate_with_file_and_fragment():
    """Test fragment resolution with a schema loaded from a file"""
    import json
    import os

    # Get the path to the test schema file
    schema_path = os.path.join(
        os.path.dirname(__file__), "test_schema_with_fragment.json"
    )

    # Load the schema from file
    with open(schema_path, "r") as file:
        schema_data = json.load(file)

    schema = Schema.from_raw_data(
        schema_data, base_uri=f"file://{schema_path}#/definitions/Person"
    )

    generator = JSONSchemaGenerator(schema)

    # Generate data
    result = generator.generate()

    # Verify the Person fragment was resolved and properties are present
    assert "user" not in result, "Generated should not have 'user' property"
    assert "firstName" in result, "User missing 'firstName' property"
    assert "lastName" in result, "User missing 'lastName' property"
    assert "age" in result, "User missing 'age' property"
    assert isinstance(
        result["firstName"], str
    ), "User firstName should be a string"
    assert isinstance(
        result["lastName"], str
    ), "User lastName should be a string"
    assert isinstance(result["age"], int), "User age should be an integer"
    assert 18 <= result["age"] <= 100, "User age should be between 18 and 100"


def test_recursive_schema():
    # Recursive schema example
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "children": {
                "type": "array",
                "items": {"$ref": "#"},  # Recursive reference
                "minItems": 1,
                "maxItems": 1,
            },
        },
    }

    recursive_schema = Schema(
        data=schema_data, base_uri="file://recursive.json"
    )
    generator = JSONSchemaGenerator(recursive_schema)

    # Ensure the generator can produce a result without infinite recursion
    try:
        result = generator.generate()
    except RecursionError:
        pytest.fail("JSONSchemaGenerator failed to handle recursive schema.")

    assert isinstance(result, dict)  # Root should be an object
    assert "name" in result
    assert isinstance(result["name"], str)
    assert "children" in result
    assert isinstance(result["children"], list)
    assert len(result["children"]) == 1
    child = result["children"][0]
    if child is not None:
        assert isinstance(child, dict)

    # Recursive schema with lazy $ref
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "child": {"$ref": "#"},
        },
    }

    recursive_lazy_schema = Schema(
        data=schema_data, base_uri="file://recursive-lazy.json"
    )
    generator = JSONSchemaGenerator(recursive_lazy_schema)

    # Generate a sample and ensure it resolves lazily
    sample = generator.generate()

    assert isinstance(sample, dict)
    assert "name" in sample
    assert isinstance(sample["name"], str)

    # Ensure "child" is resolved lazily and does not cause infinite recursion
    assert "child" in sample
    assert isinstance(sample["child"], dict) or sample["child"] is None


def test_recursive_schema_with_repeated_generators():
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "child": {"$ref": "#"},
        },
    }

    schema = Schema(
        data=schema_data,
        base_uri="file://recursive-reuse.json",
    )

    first_generator = JSONSchemaGenerator(schema)
    first_result = first_generator.generate()

    # Original schema should remain untouched so it can be reused safely
    assert schema.data == schema_data

    second_generator = JSONSchemaGenerator(schema)
    second_result = second_generator.generate()

    assert isinstance(first_result, dict)
    assert isinstance(second_result, dict)
