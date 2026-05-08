from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def _gen(schema_data, **scenario_kwargs):
    schema = Schema(base_uri="file://dummy.json", data=schema_data)
    scenario = Scenario(name="t", scenario_only=True, **scenario_kwargs)
    return JSONSchemaGenerator(schema=schema, scenario=scenario).generate()


# ---------------------------------------------------------------------------
# 1. Empty scenario → empty output even when all fields are required
# ---------------------------------------------------------------------------
def test_scenario_only_empty_scenario_produces_empty():
    schema_data = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
    }
    result = _gen(schema_data)
    assert result == {}


# ---------------------------------------------------------------------------
# 2. Single override → only that field appears
# ---------------------------------------------------------------------------
def test_scenario_only_single_override():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "desc": {"type": "string"},
        },
    }
    result = _gen(schema_data, overrides={"id": "X"})
    assert result == {"id": "X"}


# ---------------------------------------------------------------------------
# 3. Nested override materialises ancestor object but not siblings
# ---------------------------------------------------------------------------
def test_scenario_only_nested_override_prunes_siblings():
    schema_data = {
        "type": "object",
        "required": ["address"],
        "properties": {
            "name": {"type": "string"},
            "address": {
                "type": "object",
                "required": ["street", "city"],
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                },
            },
        },
    }
    result = _gen(schema_data, overrides={"address.city": "NYC"})
    assert "name" not in result
    assert "address" in result
    assert result["address"] == {"city": "NYC"}
    assert "street" not in result["address"]


# ---------------------------------------------------------------------------
# 4. pattern_override matches every path containing the substring
# ---------------------------------------------------------------------------
def test_scenario_only_pattern_override():
    schema_data = {
        "type": "object",
        "properties": {
            "firstName": {"type": "string"},
            "lastName": {"type": "string"},
            "age": {"type": "integer"},
        },
    }
    result = _gen(
        schema_data,
        pattern_overrides=[("Name", lambda ctx: "n")],
    )
    assert result.get("firstName") == "n"
    assert result.get("lastName") == "n"
    assert "age" not in result


# ---------------------------------------------------------------------------
# 5. default_data alone seeds covered fields
# ---------------------------------------------------------------------------
def test_scenario_only_default_data():
    schema_data = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "extra": {"type": "string"},
        },
    }
    result = _gen(schema_data, default_data={"id": "seed"})
    assert result.get("id") == "seed"
    assert "extra" not in result


# ---------------------------------------------------------------------------
# 6. oneof_selectors picks branch; only override field inside appears
# ---------------------------------------------------------------------------
def test_scenario_only_oneof_selector_with_override():
    schema_data = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "const": "cat"},
                    "purrs": {"type": "boolean"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "const": "dog"},
                    "barks": {"type": "boolean"},
                },
            },
        ]
    }
    result = _gen(
        schema_data,
        oneof_selectors={"": 0},
        overrides={"purrs": True},
    )
    assert result == {"purrs": True}
    assert "kind" not in result
    assert "barks" not in result


# ---------------------------------------------------------------------------
# 7. Array omitted when no pattern covers its items
# ---------------------------------------------------------------------------
def test_scenario_only_array_omitted_without_coverage():
    schema_data = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "id": {"type": "string"},
        },
    }
    result = _gen(schema_data, overrides={"id": "1"})
    assert result == {"id": "1"}
    assert "tags" not in result


# ---------------------------------------------------------------------------
# 8. Array items populated when pattern covers them
# ---------------------------------------------------------------------------
def test_scenario_only_array_populated_by_pattern():
    schema_data = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "string"},
            },
        },
    }
    result = _gen(
        schema_data,
        pattern_overrides=[("tags[", lambda ctx: "t")],
    )
    assert result.get("tags") == ["t", "t"]


# ---------------------------------------------------------------------------
# 9. default_data array preserved; no extra items added
# ---------------------------------------------------------------------------
def test_scenario_only_default_data_array_preserved():
    schema_data = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "maxItems": 5,
                "items": {"type": "string"},
            },
            "other": {"type": "string"},
        },
    }
    result = _gen(schema_data, default_data={"tags": ["a", "b"]})
    assert result.get("tags") == ["a", "b"]
    assert "other" not in result


# ---------------------------------------------------------------------------
# 10. Required field without coverage is absent (not leaked via minimal_mode)
# ---------------------------------------------------------------------------
def test_scenario_only_required_field_omitted_without_coverage():
    schema_data = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
    }
    result = _gen(schema_data, overrides={"id": "x"})
    assert result == {"id": "x"}
    assert "name" not in result


# ---------------------------------------------------------------------------
# 11. Combined scenario_only=True + minimal_mode=True behaves like scenario_only
# ---------------------------------------------------------------------------
def test_scenario_only_wins_over_minimal_mode():
    schema_data = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "opt": {"type": "string"},
        },
    }
    schema = Schema(base_uri="file://dummy.json", data=schema_data)
    scenario = Scenario(
        name="t",
        scenario_only=True,
        minimal_mode=True,
        overrides={"opt": "v"},
    )
    result = JSONSchemaGenerator(schema=schema, scenario=scenario).generate()
    # Only opt covered; required id/name should still be absent
    assert result == {"opt": "v"}
