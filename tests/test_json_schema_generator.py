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
