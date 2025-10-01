from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def test_scenario_default_data_initializes_result():
    # Schema defines a simple object with properties
    schema_data = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "nested": {
                "type": "object",
                "properties": {
                    "flag": {"type": "boolean"},
                    "count": {"type": "integer"},
                },
            },
        },
    }

    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    # Provide default data in scenario
    scenario = Scenario(
        name="with-defaults",
        default_data={
            "name": "Alice",
            "nested": {"flag": True},
            "not_present_in_schema": "should be ignored",
        },
    )

    gen = JSONSchemaGenerator(schema=schema, scenario=scenario)

    result = gen.generate()

    # Ensure defaults are present
    assert result["name"] == "Alice"
    assert result["nested"]["flag"] is True

    # Ensure generator still fills in other fields
    assert isinstance(result["age"], int)
    assert "count" in result["nested"]
    assert isinstance(result["nested"]["count"], int)
    assert "not_present_in_schema" not in result


def test_scenario_default_data_is_merged_not_overwritten():
    schema_data = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {"inner": {"type": "string"}},
            }
        },
    }
    schema = Schema(base_uri="file://dummy.json", data=schema_data)

    # default_data pre-creates nested structure
    scenario = Scenario(
        name="merge-defaults", default_data={"outer": {"pre": 1}}
    )

    gen = JSONSchemaGenerator(schema=schema, scenario=scenario)
    res = gen.generate()

    # Default preserved and schema-driven fields added
    assert res["outer"]["pre"] == 1
    assert "inner" in res["outer"]
