from __future__ import annotations

import concurrent.futures

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_parallel_generation():
    """Test that the generator can be used in parallel."""
    # Create a simple schema
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "city": {"type": "string"},
        },
    }
    schema = Schema(data=schema_data)

    # Create scenarios with different overrides
    # We need to avoid the lambda capture issue in list comprehension
    scenarios = []
    for i in range(10):
        # Use a helper function to create a properly scoped lambda
        def make_overrides(idx):
            return {
                "name": lambda ctx: f"Person {idx}",
                "age": lambda ctx: 20 + idx,
                "city": lambda ctx: [
                    "New York",
                    "London",
                    "Paris",
                    "Tokyo",
                    "Berlin",
                ][idx % 5],
            }

        scenarios.append(
            Scenario(name=f"scenario_{i}", overrides=make_overrides(i))
        )

    # Create the generator
    generator = JSONSchemaGenerator(schema=schema)

    # Generate data in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(generator.generate, scenario)
            for scenario in scenarios
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    # Verify we have 10 different results
    assert len(results) == 10

    # Check that all expected data is present and unique
    names = set(result["name"] for result in results)
    ages = set(result["age"] for result in results)

    # All names should be different
    assert len(names) == 10

    # All ages should be different
    assert len(ages) == 10

    # Each result should match its corresponding scenario
    for i, scenario in enumerate(scenarios):
        expected_name = f"Person {i}"
        expected_age = 20 + i

        # Find the matching result
        matching_result = next(
            (
                r
                for r in results
                if r["name"] == expected_name and r["age"] == expected_age
            ),
            None,
        )

        assert (
            matching_result is not None
        ), f"Could not find result for scenario {i}"


def test_sequential_vs_parallel():
    """Test that parallel and sequential generation produce the same results."""
    # Create a simple schema
    schema_data = {
        "type": "object",
        "properties": {"id": {"type": "string"}, "value": {"type": "integer"}},
    }
    schema = Schema(data=schema_data)

    # Create a test scenario
    scenario = Scenario(
        name="test_scenario",
        overrides={"id": lambda ctx: "test-id", "value": lambda ctx: 42},
    )

    # Create the generator
    generator = JSONSchemaGenerator(schema=schema)

    # Generate sequentially first
    sequential_results = [generator.generate(scenario) for _ in range(5)]

    # Generate in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(generator.generate, scenario) for _ in range(5)
        ]
        parallel_results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    # Both should have the same content
    for result in sequential_results + parallel_results:
        assert result == {"id": "test-id", "value": 42}
