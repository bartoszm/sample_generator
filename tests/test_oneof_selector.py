from __future__ import annotations

import random

import pytest

from src.json_sample_generator import JSONSchemaGenerator
from src.json_sample_generator.models import Scenario, Schema

# ---------------------------------------------------------------------------
# Basic selector return shapes: int, dict (schema), str (title)
# ---------------------------------------------------------------------------


def _pet_strings_schema() -> Schema:
    return Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {"type": "string", "const": "dog"},
                        {"type": "string", "const": "cat"},
                        {"type": "string", "const": "bird"},
                    ]
                }
            },
        }
    )


def test_oneof_selector_index():
    scenario = Scenario(
        name="oneof_index",
        oneof_selectors={"pet": lambda ctx, schemas: 1},
    )
    result = JSONSchemaGenerator(schema=_pet_strings_schema()).generate(
        scenario
    )
    assert result["pet"] == "cat"


def test_oneof_selector_schema():
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "dog"}},
                        },
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "cat"}},
                        },
                    ]
                }
            },
        }
    )
    scenario = Scenario(
        name="oneof_schema",
        oneof_selectors={"pet": lambda ctx, schemas: schemas[0]},
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"]["kind"] == "dog"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_oneof_empty_raises():
    schema = Schema(
        data={
            "type": "object",
            "properties": {"pet": {"oneOf": []}},
        }
    )
    with pytest.raises(ValueError, match="no candidates"):
        JSONSchemaGenerator(schema=schema).generate(Scenario(name="x"))


def test_oneof_selector_out_of_range():
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: 99}
    )
    with pytest.raises(IndexError, match="out-of-range index 99"):
        JSONSchemaGenerator(schema=_pet_strings_schema()).generate(scenario)


def test_oneof_selector_negative_index():
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: -1}
    )
    with pytest.raises(IndexError, match="out-of-range index -1"):
        JSONSchemaGenerator(schema=_pet_strings_schema()).generate(scenario)


def test_oneof_selector_bool_rejected():
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: True}
    )
    with pytest.raises(TypeError, match="returned a bool"):
        JSONSchemaGenerator(schema=_pet_strings_schema()).generate(scenario)


def test_oneof_selector_none_rejected():
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: None}
    )
    with pytest.raises(TypeError, match="returned NoneType"):
        JSONSchemaGenerator(schema=_pet_strings_schema()).generate(scenario)


def test_oneof_selector_bad_return_type_rejected():
    # Returning a list (not int/str/dict) is a user bug.
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: [0]}
    )
    with pytest.raises(TypeError, match="returned list"):
        JSONSchemaGenerator(schema=_pet_strings_schema()).generate(scenario)


# ---------------------------------------------------------------------------
# Selection by title / discriminator
# ---------------------------------------------------------------------------


def _titled_pet_schema() -> Schema:
    return Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {
                            "title": "Dog",
                            "type": "object",
                            "properties": {"kind": {"const": "dog"}},
                        },
                        {
                            "title": "Cat",
                            "type": "object",
                            "properties": {"kind": {"const": "cat"}},
                        },
                    ]
                }
            },
        }
    )


def test_oneof_selector_by_title():
    scenario = Scenario(
        name="by_title",
        oneof_selectors={"pet": lambda ctx, schemas: "Cat"},
    )
    result = JSONSchemaGenerator(schema=_titled_pet_schema()).generate(
        scenario
    )
    assert result["pet"]["kind"] == "cat"


def test_oneof_selector_by_discriminator_const():
    # No titles — rely on properties.kind.const as the discriminator value.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "discriminator": {"propertyName": "kind"},
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "dog"}},
                        },
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "cat"}},
                        },
                    ],
                }
            },
        }
    )
    scenario = Scenario(
        name="by_disc_const",
        oneof_selectors={"pet": lambda ctx, schemas: "cat"},
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"]["kind"] == "cat"


def test_oneof_selector_by_discriminator_mapping():
    # discriminator.mapping points to a ref; we match on the ref's tail
    # segment against the candidate's title.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {
                            "dog": "#/components/schemas/Dog",
                            "cat": "#/components/schemas/Cat",
                        },
                    },
                    "oneOf": [
                        {
                            "title": "Dog",
                            "type": "object",
                            "properties": {"kind": {"const": "dog"}},
                        },
                        {
                            "title": "Cat",
                            "type": "object",
                            "properties": {"kind": {"const": "cat"}},
                        },
                    ],
                }
            },
        }
    )
    scenario = Scenario(
        name="by_disc_mapping",
        oneof_selectors={"pet": lambda ctx, schemas: "cat"},
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"]["kind"] == "cat"


def test_oneof_selector_unknown_string_raises():
    scenario = Scenario(
        name="x",
        oneof_selectors={"pet": lambda ctx, schemas: "snake"},
    )
    with pytest.raises(ValueError, match="snake"):
        JSONSchemaGenerator(schema=_titled_pet_schema()).generate(scenario)


# ---------------------------------------------------------------------------
# normalize() ergonomic shortcuts: bare int / str / dict
# ---------------------------------------------------------------------------


def test_oneof_bare_int_in_oneof_selectors():
    scenario = Scenario(name="x", oneof_selectors={"pet": 2}).normalize()
    result = JSONSchemaGenerator(schema=_pet_strings_schema()).generate(
        scenario
    )
    assert result["pet"] == "bird"


def test_oneof_bare_string_in_oneof_selectors():
    scenario = Scenario(name="x", oneof_selectors={"pet": "Cat"}).normalize()
    result = JSONSchemaGenerator(schema=_titled_pet_schema()).generate(
        scenario
    )
    assert result["pet"]["kind"] == "cat"


def test_oneof_bare_dict_in_oneof_selectors():
    custom = {"type": "string", "const": "literal"}
    scenario = Scenario(name="x", oneof_selectors={"pet": custom}).normalize()
    result = JSONSchemaGenerator(schema=_pet_strings_schema()).generate(
        scenario
    )
    assert result["pet"] == "literal"


# ---------------------------------------------------------------------------
# Regex matching semantics
# ---------------------------------------------------------------------------


def test_oneof_selector_regex_pattern():
    # Array of oneOf items; a regex key matches every concrete index.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "oneOf": [
                            {"type": "string", "const": "A"},
                            {"type": "string", "const": "B"},
                        ]
                    },
                }
            },
        }
    )
    scenario = Scenario(
        name="x",
        oneof_selectors={r"items\[\d+\]": lambda ctx, schemas: 1},
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["items"] == ["B", "B", "B"]


def test_oneof_selector_exact_key_beats_regex():
    # Both an exact key and a catch-all regex match; exact wins.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {"type": "string", "const": "dog"},
                        {"type": "string", "const": "cat"},
                    ]
                }
            },
        }
    )
    scenario = Scenario(
        name="x",
        oneof_selectors={
            r".*": lambda ctx, schemas: 0,  # would pick dog
            "pet": lambda ctx, schemas: 1,  # exact wins → cat
        },
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"] == "cat"


def test_oneof_selector_regex_insertion_order():
    # Two regex keys both match; first-inserted wins.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {"type": "string", "const": "dog"},
                        {"type": "string", "const": "cat"},
                    ]
                }
            },
        }
    )
    scenario = Scenario(
        name="x",
        oneof_selectors={
            r"p.t": lambda ctx, schemas: 0,  # matches "pet" → dog
            r".*": lambda ctx, schemas: 1,  # also matches → ignored
        },
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"] == "dog"


def test_oneof_selector_no_false_substring_match():
    # Before the regex switch, key "pet" matched "profile.pet_name"
    # via `in`. With re.fullmatch it must not match → random fallback.
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "properties": {
                        "pet_name": {
                            "oneOf": [
                                {"type": "string", "const": "a"},
                                {"type": "string", "const": "b"},
                            ]
                        }
                    },
                }
            },
        }
    )
    # A selector keyed on "pet" would have picked index 0 under the old
    # substring logic. Under fullmatch it does not fire, so random chooses.
    scenario = Scenario(
        name="x",
        oneof_selectors={"pet": lambda ctx, schemas: 0},
    )
    random.seed(0)
    gen = JSONSchemaGenerator(schema=schema)
    # Across several seeds both branches should appear, confirming the
    # selector is ignored.
    seen = set()
    for seed in range(20):
        random.seed(seed)
        seen.add(gen.generate(scenario)["profile"]["pet_name"])
    assert seen == {"a", "b"}


def test_oneof_selector_invalid_regex_ignored():
    # An unparseable regex must not crash generation — it's simply skipped.
    scenario = Scenario(
        name="x",
        oneof_selectors={"[unclosed": lambda ctx, schemas: 0},
    )
    # Should pick randomly, not raise.
    random.seed(0)
    result = JSONSchemaGenerator(schema=_pet_strings_schema()).generate(
        scenario
    )
    assert result["pet"] in {"dog", "cat", "bird"}


# ---------------------------------------------------------------------------
# Structural cases: root, nested, oneOf inside anyOf
# ---------------------------------------------------------------------------


def test_oneof_selector_root_path():
    # The generator returns a dict at the root, so exercise the root-path
    # selector with object variants and inspect the chosen branch's marker.
    schema = Schema(
        data={
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"which": {"const": "A"}},
                },
                {
                    "type": "object",
                    "properties": {"which": {"const": "B"}},
                },
            ]
        }
    )
    scenario = Scenario(name="x", oneof_selectors={"": lambda ctx, schemas: 1})
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["which"] == "B"


def test_oneof_selector_nested():
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {
                                "tag": {
                                    "oneOf": [
                                        {"type": "string", "const": "x"},
                                        {"type": "string", "const": "y"},
                                    ]
                                }
                            },
                        },
                        {"type": "string", "const": "other"},
                    ]
                }
            },
        }
    )
    scenario = Scenario(
        name="nested",
        oneof_selectors={
            "pet": lambda ctx, schemas: 0,
            "pet.tag": lambda ctx, schemas: 1,
        },
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["pet"]["tag"] == "y"


def test_oneof_selector_inside_anyof():
    schema = Schema(
        data={
            "type": "object",
            "properties": {
                "v": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "oneOf": [
                                        {"type": "string", "const": "p"},
                                        {"type": "string", "const": "q"},
                                    ]
                                }
                            },
                        },
                        {"type": "string", "const": "scalar"},
                    ]
                }
            },
        }
    )
    scenario = Scenario(
        name="anyof_oneof",
        oneof_selectors={
            "v": lambda ctx, schemas: 0,  # anyOf picks object branch
            "v.kind": lambda ctx, schemas: 1,  # oneOf picks "q"
        },
    )
    result = JSONSchemaGenerator(schema=schema).generate(scenario)
    assert result["v"]["kind"] == "q"


# ---------------------------------------------------------------------------
# anyOf: new selector support
# ---------------------------------------------------------------------------


def _pet_anyof_schema() -> Schema:
    return Schema(
        data={
            "type": "object",
            "properties": {
                "pet": {
                    "anyOf": [
                        {"title": "Dog", "type": "string", "const": "dog"},
                        {"title": "Cat", "type": "string", "const": "cat"},
                    ]
                }
            },
        }
    )


def test_anyof_selector_index():
    scenario = Scenario(
        name="x", oneof_selectors={"pet": lambda ctx, schemas: 1}
    )
    result = JSONSchemaGenerator(schema=_pet_anyof_schema()).generate(scenario)
    assert result["pet"] == "cat"


def test_anyof_selector_by_title():
    scenario = Scenario(name="x", oneof_selectors={"pet": "Dog"}).normalize()
    result = JSONSchemaGenerator(schema=_pet_anyof_schema()).generate(scenario)
    assert result["pet"] == "dog"


def test_anyof_no_selector_random():
    # No selector → random pick from the anyOf (preserves old behavior).
    seen = set()
    gen = JSONSchemaGenerator(schema=_pet_anyof_schema())
    for seed in range(20):
        random.seed(seed)
        seen.add(gen.generate(Scenario(name="x"))["pet"])
    assert seen == {"dog", "cat"}


def test_anyof_empty_raises():
    schema = Schema(
        data={
            "type": "object",
            "properties": {"pet": {"anyOf": []}},
        }
    )
    with pytest.raises(ValueError, match="no candidates"):
        JSONSchemaGenerator(schema=schema).generate(Scenario(name="x"))


# ---------------------------------------------------------------------------
# Determinism under seed (regression guard)
# ---------------------------------------------------------------------------


def test_oneof_no_selectors_deterministic_under_seed():
    gen = JSONSchemaGenerator(schema=_pet_strings_schema())
    random.seed(42)
    a = gen.generate(Scenario(name="x"))
    random.seed(42)
    b = gen.generate(Scenario(name="x"))
    assert a == b


# ---------------------------------------------------------------------------
# variant_selectors alias
# ---------------------------------------------------------------------------


def test_variant_selectors_alias_is_same_dict():
    s = Scenario(name="x", oneof_selectors={"pet": lambda ctx, schemas: 0})
    assert s.variant_selectors is s.oneof_selectors
    # Mutating through the alias is visible on the canonical field.
    s.variant_selectors["other"] = lambda ctx, schemas: 1
    assert "other" in s.oneof_selectors
