from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def create_user_schema() -> Schema:
    """Create a simple schema for a user object."""
    schema_data = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "age": {"type": "integer", "minimum": 18},
            "is_active": {"type": "boolean"},
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "country": {"type": "string"},
                    "zip": {"type": "string"},  # Added zip field
                },
            },
            "interests": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "name", "email"],
    }
    return Schema(data=schema_data)


def simple_values_example() -> None:
    """Example of using simple value overrides in scenarios."""
    print("\n=== Simple Value Overrides Example ===\n")

    # Create schema and generator
    schema = create_user_schema()
    generator = JSONSchemaGenerator(schema=schema)

    # Create a scenario with simple value overrides (no lambdas)
    scenario = Scenario(
        name="simple_override_scenario",
        overrides={
            "id": "user-12345",
            "name": "John Smith",
            "email": "john.smith@example.com",
            "age": 35,
            "is_active": True,
            "address.street": "123 Main St",
            "address.city": "Anytown",
            "address.country": "USA",
            "interests": ["reading", "coding", "hiking"],
            # You can use None for fields that should be null/None
            "address.zip": None,
        },
    )

    # Generate with the simple value scenario
    result = generator.generate(scenario)
    print("Simple values scenario result:")
    print(f"ID: {result['id']}")
    print(f"Name: {result['name']}")
    print(f"Email: {result['email']}")
    print(f"Age: {result['age']}")
    print(f"Active: {result['is_active']}")
    print(
        f"Address: {result['address']['street']}, {result['address']['city']}, {result['address']['country']}"
    )
    print(f"Zip: {result['address']['zip']} (This is None)")
    print(f"Interests: {', '.join(result['interests'])}")
    print()


def mixed_overrides_example() -> None:
    """Example of using a mix of simple values and lambda functions."""
    print("\n=== Mixed Overrides Example ===\n")

    # Create schema and generator
    schema = create_user_schema()
    generator = JSONSchemaGenerator(schema=schema)

    # Create scenarios for different user types
    scenarios = {
        "admin": Scenario(
            name="admin_scenario",
            overrides={
                "id": "admin-001",  # Simple value
                "name": "Admin User",  # Simple value
                "email": "admin@example.com",  # Simple value
                "age": lambda ctx: 40,  # Lambda (could be simple value)
                "is_active": True,  # Simple value
                "address.country": "USA",  # Simple value
                "interests": [
                    "administration",
                    "security",
                ],  # Simple value (list)
            },
        ),
        "customer": Scenario(
            name="customer_scenario",
            overrides={
                "id": lambda ctx: f"cust-{1000}",  # Lambda with calculation
                "name": "Regular Customer",  # Simple value
                "email": "customer@example.com",  # Simple value
                "age": 25,  # Simple value
                "is_active": lambda ctx: True,  # Lambda (could be simple value)
                "address.country": "Canada",  # Simple value
                "interests": ["shopping", "products"],  # Simple value (list)
            },
        ),
    }

    # Generate with different scenarios
    for user_type, scenario in scenarios.items():
        result = generator.generate(scenario)
        print(f"{user_type.upper()} scenario result:")
        print(f"ID: {result['id']}")
        print(f"Name: {result['name']}")
        print(f"Email: {result['email']}")
        print(f"Age: {result['age']}")
        print(f"Active: {result['is_active']}")
        print(f"Country: {result['address']['country']}")
        print(f"Interests: {', '.join(result['interests'])}")
    print()


if __name__ == "__main__":
    # Run the examples
    simple_values_example()
    mixed_overrides_example()
