"""Break scenarios resolve schema fragments along array paths."""

from __future__ import annotations

import jsonschema
import pytest

from json_sample_generator.breaker import SampleBreaker
from json_sample_generator.models import Schema
from json_sample_generator.models.break_models import (
    BreakKind,
    BreakRule,
    BreakScenario,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 3},
                    "m": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        }
    },
}
DATA = {"items": [{"name": "abc", "m": [[1, 2]]}]}


def test_resolve_schema_walks_array_paths():
    breaker = SampleBreaker(Schema(data=SCHEMA))
    assert breaker._resolve_schema(DATA, "items")["type"] == "array"
    assert breaker._resolve_schema(DATA, "items[0]")["type"] == "object"
    assert breaker._resolve_schema(DATA, "items[0].name") == {
        "type": "string",
        "maxLength": 3,
    }
    assert breaker._resolve_schema(DATA, "items[0].m[0][0]") == {
        "type": "integer",
        "minimum": 1,
    }


@pytest.mark.parametrize(
    "path, kind, expected",
    [
        ("items[0].name", BreakKind.MAX_LENGTH_VIOLATION, "xxxx"),
        ("items[0].m[0][0]", BreakKind.MIN_VIOLATION, 0),
    ],
)
def test_break_rule_on_array_item_property(path, kind, expected):
    scenario = BreakScenario(name="t", rules=[BreakRule(path=path, kind=kind)])
    broken = SampleBreaker(Schema(data=SCHEMA)).apply(DATA, scenario)
    node = broken
    for segment in ("items", 0):
        node = node[segment]
    value = node["name"] if path.endswith("name") else node["m"][0][0]
    assert value == expected
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(broken, SCHEMA)
