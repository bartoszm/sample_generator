from __future__ import annotations

from jsonref import replace_refs

from src.json_sample_generator.helpers.utils import (
    contains_itself,
    parse_path,
    set_value_at_path,
    unwrap_ref,
)


def test_parse_path_simple() -> None:
    assert parse_path("a.b.c") == ["a", "b", "c"], "should parse dotted keys"


def test_parse_path_with_index() -> None:
    assert parse_path("items[0].name") == [
        "items",
        0,
        "name",
    ], "should parse keys with indices"


def test_parse_at_type() -> None:
    target: dict[str, dict[str, int]] = {}
    set_value_at_path("@type", target, 10)
    assert target["@type"] == 10, "should set 10"


def test_set_value_top_level_dict() -> None:
    target: dict[str, int] = {}
    ret = set_value_at_path("x", target, 5)
    assert ret == 5, "should return the set value"
    assert target == {"x": 5}, "should set top-level key"


def test_set_value_nested_dict() -> None:
    target: dict[str, dict[str, int]] = {}
    set_value_at_path("a.b", target, 10)
    assert target["a"]["b"] == 10, "should set nested dict value"


def test_set_value_list_extension() -> None:
    target: dict[str, list[dict[str, int]]] = {}
    set_value_at_path("items[2].count", target, 7)
    lst = target["items"]
    assert isinstance(lst, list), "should create a list for items"
    assert len(lst) == 3, "list should be extended to index 2"
    assert (
        lst[0] == {} and lst[1] == {}
    ), "indices 0 and 1 should be empty dicts"
    assert lst[2] == {"count": 7}, "index 2 should be dict with count"


def test_overwrite_existing_value() -> None:
    target = {"a": {"b": 1}}
    set_value_at_path("a.b", target, 2)
    assert target["a"]["b"] == 2, "should overwrite existing value"


def test_contains_itself() -> None:
    looped: dict = {"type": "object", "properties": {}}
    looped["properties"]["child"] = looped
    listed: list = []
    listed.append(listed)
    shared = {"type": "string"}
    assert contains_itself(looped)
    assert contains_itself({"allOf": listed})
    # the same dict reached twice is not a cycle
    assert not contains_itself({"properties": {"a": shared, "b": shared}})
    assert not contains_itself({"type": "string"})


def test_contains_itself_through_a_json_ref() -> None:
    raw = {"type": "object", "properties": {"child": {"$ref": "#"}}}
    assert contains_itself(replace_refs(raw))
    assert not contains_itself(raw)


def test_unwrap_ref() -> None:
    node = {"type": "string"}
    ref = replace_refs({"a": node, "b": {"$ref": "#/a"}})["b"]
    assert unwrap_ref(ref) == node
    assert unwrap_ref(node) is node
    assert unwrap_ref("text") == "text"


def test_unwrap_ref_returns_an_unresolvable_ref_as_it_is() -> None:
    ref = replace_refs({"b": {"$ref": "#/missing"}})["b"]
    assert unwrap_ref(ref) is ref
