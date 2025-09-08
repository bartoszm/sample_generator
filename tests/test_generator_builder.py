from src.json_sample_generator import (
    JSONSchemaGenerator,
    SchemaGeneratorBuilder,
)
from src.json_sample_generator.models import Scenario, Schema


def test_generator_builder_pattern():
    """Test that the generator uses the builder pattern correctly."""
    # Create a simple schema
    schema_data = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    }
    schema = Schema(data=schema_data)

    # Create a default scenario with an override
    default_scenario = Scenario(
        name="default_scenario",
        overrides={"name": lambda ctx: "John Doe", "age": lambda ctx: 30},
    )

    # Create the generator with the default scenario
    generator = JSONSchemaGenerator(schema=schema, scenario=default_scenario)

    # Generate the data using the default scenario
    result = generator.generate()

    # Verify the result
    assert result == {"name": "John Doe", "age": 30}

    # Create an alternative scenario
    alt_scenario = Scenario(
        name="alternative_scenario",
        overrides={"name": lambda ctx: "Jane Smith", "age": lambda ctx: 25},
    )

    # Generate data using the alternative scenario
    alt_result = generator.generate(alt_scenario)

    # Verify the alternative result
    assert alt_result == {"name": "Jane Smith", "age": 25}


def test_builder_direct_usage():
    """Test that we can use the builder directly."""
    # Create a builder
    builder = SchemaGeneratorBuilder()

    # Set values directly
    builder.set_value_at_path("name", "Jane Doe")
    builder.set_value_at_path("age", 25)

    # Get the result
    result = builder.get_result()

    # Verify the result
    assert result == {"name": "Jane Doe", "age": 25}


def test_nested_paths():
    """Test that the builder works with nested paths."""
    # Create a builder
    builder = SchemaGeneratorBuilder()

    # Set values at nested paths
    builder.set_value_at_path("person.name", "Bob Smith")
    builder.set_value_at_path("person.age", 40)
    builder.set_value_at_path("person.address.city", "New York")

    # Get the result
    result = builder.get_result()

    # Verify the result
    expected = {
        "person": {
            "name": "Bob Smith",
            "age": 40,
            "address": {"city": "New York"},
        }
    }
    assert result == expected


def test_array_paths():
    """Test that the builder works with array paths."""
    # Create a builder
    builder = SchemaGeneratorBuilder()

    # Set values at array paths
    builder.set_value_at_path("people[0].name", "Alice")
    builder.set_value_at_path("people[0].age", 35)
    builder.set_value_at_path("people[1].name", "Bob")
    builder.set_value_at_path("people[1].age", 40)

    # Get the result
    result = builder.get_result()

    # Verify the result
    expected = {
        "people": [{"name": "Alice", "age": 35}, {"name": "Bob", "age": 40}]
    }
    assert result == expected
