from __future__ import annotations

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema


def _gen(schema_data, **scenario_kwargs):
    schema = Schema(base_uri="file://dummy.json", data=schema_data)
    scenario = Scenario(name="test", minimal_mode=True, **scenario_kwargs)
    return JSONSchemaGenerator(schema=schema, scenario=scenario).generate()


# ---------------------------------------------------------------------------
# 1. Basic: only required fields emitted
# ---------------------------------------------------------------------------
def test_minimal_only_required_fields():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "desc": {"type": "string"},
        },
    }
    result = _gen(schema_data)
    assert "id" in result
    assert "name" not in result
    assert "desc" not in result


# ---------------------------------------------------------------------------
# 2. Recursion: required nested object's own required fields enforced
# ---------------------------------------------------------------------------
def test_minimal_recursive_into_required_object():
    schema_data = {
        "type": "object",
        "required": ["address"],
        "properties": {
            "address": {
                "type": "object",
                "required": ["street"],
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                },
            },
            "notes": {"type": "string"},
        },
    }
    result = _gen(schema_data)
    assert "address" in result
    assert "street" in result["address"]
    assert "city" not in result["address"]
    assert "notes" not in result


# ---------------------------------------------------------------------------
# 3. Override forces an optional field into the result
# ---------------------------------------------------------------------------
def test_minimal_override_forces_optional_field():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "desc": {"type": "string"},
        },
    }
    result = _gen(schema_data, overrides={"desc": "hello"})
    assert "id" in result
    assert result["desc"] == "hello"


# ---------------------------------------------------------------------------
# 4. Descendant override forces the ancestor to appear
# ---------------------------------------------------------------------------
def test_minimal_descendant_override_forces_ancestor():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "nested": {
                "type": "object",
                "properties": {
                    "value": {"type": "integer"},
                    "extra": {"type": "string"},
                },
            },
        },
    }
    result = _gen(schema_data, overrides={"nested.value": 42})
    assert "id" in result
    assert "nested" in result
    assert result["nested"]["value"] == 42
    # extra is optional and not overridden — must be absent
    assert "extra" not in result["nested"]


# ---------------------------------------------------------------------------
# 5. default_data forces a field into the result
# ---------------------------------------------------------------------------
def test_minimal_default_data_forces_field():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "nested": {
                "type": "object",
                "properties": {
                    "pre": {"type": "integer"},
                    "other": {"type": "string"},
                },
            },
        },
    }
    result = _gen(schema_data, default_data={"nested": {"pre": 7}})
    assert "nested" in result
    # The pre-seeded value is preserved
    assert result["nested"]["pre"] == 7
    # other is optional and not seeded — absent
    assert "other" not in result["nested"]


# ---------------------------------------------------------------------------
# 6. pattern_override does NOT force an optional field into the result
# ---------------------------------------------------------------------------
def test_minimal_pattern_override_does_not_force_field():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "desc": {"type": "string"},
        },
    }
    # Pattern would match "desc" if it were present, but minimal mode
    # should NOT pull in the optional field just because a pattern covers it.
    result = _gen(schema_data, pattern_overrides=[("desc", "from-pattern")])
    assert "id" in result
    assert "desc" not in result


# ---------------------------------------------------------------------------
# 7. allOf: unioned required from both branches, optionals omitted
# ---------------------------------------------------------------------------
def test_minimal_allof_unions_required():
    schema_data = {
        "allOf": [
            {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "opt_a": {"type": "string"},
                },
            },
            {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"type": "integer"},
                    "opt_b": {"type": "string"},
                },
            },
        ]
    }
    result = _gen(schema_data)
    assert "id" in result
    assert "code" in result
    assert "opt_a" not in result
    assert "opt_b" not in result


# ---------------------------------------------------------------------------
# 8. oneOf + selector: only selected branch's required fields appear
# ---------------------------------------------------------------------------
def test_minimal_oneof_selector_branch_required():
    schema_data = {
        "oneOf": [
            {
                "title": "TypeA",
                "type": "object",
                "required": ["a_field"],
                "properties": {
                    "a_field": {"type": "string"},
                    "a_opt": {"type": "string"},
                },
            },
            {
                "title": "TypeB",
                "type": "object",
                "required": ["b_field"],
                "properties": {
                    "b_field": {"type": "integer"},
                    "b_opt": {"type": "string"},
                },
            },
        ]
    }
    result = _gen(schema_data, oneof_selectors={"": lambda ctx, schemas: 1})
    assert "b_field" in result
    assert "b_opt" not in result
    assert "a_field" not in result


# ---------------------------------------------------------------------------
# 9. Array of objects: items obey minimal mode
# ---------------------------------------------------------------------------
def test_minimal_required_array_of_objects():
    schema_data = {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
            },
            "meta": {"type": "string"},
        },
    }
    result = _gen(schema_data)
    assert "items" in result
    assert "meta" not in result
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert "id" in item
    assert "label" not in item


# ---------------------------------------------------------------------------
# 10. Backward compat: minimal_mode=False (default) includes optional fields
# ---------------------------------------------------------------------------
def test_minimal_backward_compat_default_off():
    schema_data = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }
    schema = Schema(base_uri="file://dummy.json", data=schema_data)
    # Do NOT set minimal_mode — defaults to False
    scenario = Scenario(name="default")
    result = JSONSchemaGenerator(schema=schema, scenario=scenario).generate()
    assert "id" in result
    assert "name" in result
    assert "age" in result
