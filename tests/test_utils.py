from __future__ import annotations

from src.json_sample_generator.helpers.utils import (
    parse_path,
    set_value_at_path,
)


def test_parse_path_simple() -> None:
    assert parse_path("a.b.c") == [
        ("a", None),
        ("b", None),
        ("c", None),
    ], "should parse dotted keys"


def test_parse_path_with_index() -> None:
    assert parse_path("items[0].name") == [
        ("items", 0),
        ("name", None),
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
