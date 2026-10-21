"""Property path syntax: nested indices, root arrays and quoted keys."""

from __future__ import annotations

import pytest

from json_sample_generator import SchemaGeneratorBuilder
from json_sample_generator.helpers.utils import (
    delete_value_at_path,
    get_value_at_path,
    join_path,
    parse_path,
    set_value_at_path,
)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", []),
        ("a", ["a"]),
        ("a.b.c", ["a", "b", "c"]),
        ("items[0].name", ["items", 0, "name"]),
        ("points[0][1]", ["points", 0, 1]),
        ("[0]", [0]),
        ("[0][2].x", [0, 2, "x"]),
        ('["a.b"]', ["a.b"]),
        ('["a.b"].c[1]', ["a.b", "c", 1]),
        ('x["weird [key]"]', ["x", "weird [key]"]),
        ('["say \\"hi\\""]', ['say "hi"']),
        ('[""]', [""]),
        ("@type", ["@type"]),
        ("a.0", ["a", "0"]),
    ],
)
def test_parse_path(path, expected):
    assert parse_path(path) == expected


@pytest.mark.parametrize(
    "path",
    [".a", "a..b", "a[0]b", "a[", "a]", "a[x]", 'a["b"', "a.", "[0]a"],
)
def test_parse_path_rejects_invalid_syntax(path):
    with pytest.raises(ValueError, match="Invalid path"):
        parse_path(path)


@pytest.mark.parametrize(
    "parent, segment, expected",
    [
        ("", "a", "a"),
        ("a", "b", "a.b"),
        ("a", 0, "a[0]"),
        ("a[0]", 1, "a[0][1]"),
        ("", 0, "[0]"),
        ("", "a.b", '["a.b"]'),
        ("x", "k[1]", 'x["k[1]"]'),
        ("x", "", 'x[""]'),
        ("x", 'q"t', 'x["q\\"t"]'),
    ],
)
def test_join_path(parent, segment, expected):
    assert join_path(parent, segment) == expected


def test_join_path_round_trips_through_parse_path():
    segments = ["a.b", 0, 1, "c", "d]e", "", "plain"]
    path = ""
    for segment in segments:
        path = join_path(path, segment)
    assert parse_path(path) == segments


def test_join_path_rejects_other_types():
    with pytest.raises(TypeError):
        join_path("a", True)


def test_set_value_in_nested_lists():
    target: dict = {}
    set_value_at_path("points[0][1]", target, 2.5)
    assert target == {"points": [[None, 2.5]]}
    set_value_at_path("points[0][0]", target, 1.5)
    set_value_at_path("points[1][0]", target, 7)
    assert target == {"points": [[1.5, 2.5], [7]]}
    assert get_value_at_path("points[1][0]", target) == 7
    assert get_value_at_path("points[2][0]", target) is None


def test_set_value_on_root_list():
    target: list = []
    set_value_at_path("[1]", target, "b")
    assert target == [None, "b"]
    set_value_at_path("[0]", target, "a")
    assert target == ["a", "b"]
    assert get_value_at_path("[1]", target) == "b"


def test_set_value_with_quoted_key():
    target: dict = {}
    set_value_at_path('["a.b"].c', target, 1)
    assert target == {"a.b": {"c": 1}}
    assert get_value_at_path('["a.b"].c', target) == 1
    assert get_value_at_path("a.b.c", target) is None


def test_set_value_does_not_overwrite_when_not_forced():
    target = {"a": [1]}
    assert set_value_at_path("a[0]", target, 2, force=False) == 1
    assert set_value_at_path("b", target, 3, force=False) == 3
    assert target == {"a": [1], "b": 3}


def test_set_value_at_root_merges_dicts_and_replaces_otherwise():
    assert set_value_at_path("", {"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert set_value_at_path("", {}, [1]) == [1]


def test_delete_value_from_list_and_quoted_key():
    target = {"a.b": {"c": 1}, "xs": [1, 2, 3]}
    assert delete_value_at_path("xs[1]", target) is True
    assert target["xs"] == [1, 3]
    assert delete_value_at_path('["a.b"].c', target) is True
    assert target == {"a.b": {}, "xs": [1, 3]}
    assert delete_value_at_path("xs[5]", target) is False
    assert delete_value_at_path("nope.x", target) is False
    assert delete_value_at_path("", target) is False


def test_builder_root_can_become_a_list():
    builder = SchemaGeneratorBuilder()
    assert builder.ensure_container("", []) == []
    builder.set_value_at_path("[0]", "x")
    builder.set_value_at_path("[1]", "y")
    assert builder.get_result() == ["x", "y"]


def test_builder_ensure_container_keeps_existing_values():
    builder = SchemaGeneratorBuilder()
    builder.set_value_at_path("meta.k", 1)
    assert builder.ensure_container("meta", {}) == {"k": 1}
    assert builder.ensure_container("tags", []) == []
    assert builder.ensure_container("", {}) is builder.get_result()
    assert builder.get_result() == {"meta": {"k": 1}, "tags": []}


def test_builder_root_merge_keeps_dict_identity():
    builder = SchemaGeneratorBuilder()
    root = builder.get_result()
    builder.set_value_at_path("", {"a": 1})
    assert builder.get_result() is root
    assert root == {"a": 1}
