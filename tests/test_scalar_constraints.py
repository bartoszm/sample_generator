"""Scalar constraints in ``DefaultValueGenerator``: numeric bounds in
both the numeric and the boolean exclusive form, ``multipleOf``, RFC 3339
``date-time``/``time``, and string length combined with ``pattern`` or
``format``. Unsatisfiable schemas raise ``ValueError``."""

from __future__ import annotations

import random
import re

import pytest
from faker import Faker
from jsonschema import Draft4Validator, Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.DefaultValueGenerator import (
    DefaultValueGenerator,
    _BoundedXeger,
)
from json_sample_generator.models import Schema


def _samples(schema, n=200):
    gen = DefaultValueGenerator()(schema)
    return [gen() for _ in range(n)]


def _assert_valid(schema, values):
    # Draft 7 reads a boolean exclusiveMinimum/Maximum as a numeric bound;
    # only Draft 4 understands the boolean form.
    boolean_form = any(
        isinstance(schema.get(k), bool)
        for k in ("exclusiveMinimum", "exclusiveMaximum")
    )
    cls = Draft4Validator if boolean_form else Draft7Validator
    validator = cls(schema, format_checker=cls.FORMAT_CHECKER)
    for value in values:
        errors = [e.message for e in validator.iter_errors(value)]
        assert not errors, (value, errors)


# ---------------------------------------------------------------------------
# Numeric bounds
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "schema, check",
    [
        ({"type": "integer", "minimum": 500}, lambda v: 500 <= v <= 600),
        ({"type": "integer", "maximum": -5}, lambda v: -105 <= v <= -5),
        ({"type": "integer", "minimum": 50}, lambda v: 50 <= v <= 150),
        ({"type": "integer", "maximum": 5}, lambda v: -95 <= v <= 5),
        ({"type": "number", "minimum": 10}, lambda v: 10 <= v <= 11),
        ({"type": "number", "maximum": -2.5}, lambda v: -3.5 <= v <= -2.5),
        ({"type": "integer", "exclusiveMinimum": 200}, lambda v: v > 200),
        ({"type": "integer", "exclusiveMaximum": -200}, lambda v: v < -200),
        ({"type": "number", "exclusiveMinimum": 10}, lambda v: v > 10),
        ({"type": "number", "exclusiveMaximum": -10}, lambda v: v < -10),
    ],
)
def test_one_sided_bound_keeps_the_default_span(schema, check):
    values = _samples(schema)
    assert all(check(v) for v in values)
    _assert_valid(schema, values)


@pytest.mark.parametrize(
    "schema, check",
    [
        # draft-4 / OpenAPI 3.0 boolean form qualifies the plain bound
        (
            {"type": "integer", "minimum": 500, "exclusiveMinimum": True},
            lambda v: 500 < v <= 601,
        ),
        (
            {"type": "integer", "minimum": 10, "exclusiveMinimum": False},
            lambda v: v >= 10,
        ),
        (
            {"type": "integer", "maximum": 10, "exclusiveMaximum": True},
            lambda v: v < 10,
        ),
        (
            {
                "type": "number",
                "minimum": 10,
                "exclusiveMinimum": True,
                "maximum": 10.5,
            },
            lambda v: 10 < v <= 10.5,
        ),
        # a boolean without the plain bound is ignored
        (
            {"type": "integer", "exclusiveMinimum": True},
            lambda v: 0 <= v <= 100,
        ),
        # numeric exclusive and plain bound both given: the tighter wins
        (
            {"type": "integer", "minimum": 10, "exclusiveMinimum": 5},
            lambda v: v >= 10,
        ),
        (
            {"type": "integer", "minimum": 5, "exclusiveMinimum": 10},
            lambda v: v > 10,
        ),
        (
            {"type": "integer", "maximum": 10, "exclusiveMaximum": 20},
            lambda v: v <= 10,
        ),
        (
            {"type": "integer", "maximum": 20, "exclusiveMaximum": 10},
            lambda v: v < 10,
        ),
    ],
)
def test_exclusive_bounds_in_both_forms(schema, check):
    values = _samples(schema)
    assert all(check(v) for v in values)
    _assert_valid(schema, values)


def test_exclusive_integer_bounds_are_exact():
    schema = {
        "type": "integer",
        "exclusiveMinimum": 1.2,
        "exclusiveMaximum": 4.8,
    }
    assert set(_samples(schema)) == {2, 3, 4}


def test_narrow_open_number_range_stays_inside():
    schema = {
        "type": "number",
        "exclusiveMinimum": 1,
        "exclusiveMaximum": 1.005,
    }
    values = _samples(schema)
    assert all(1 < v < 1.005 for v in values)
    _assert_valid(schema, values)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "integer", "exclusiveMinimum": 5, "exclusiveMaximum": 6},
        {"type": "integer", "minimum": 5.2, "maximum": 5.8},
        {"type": "integer", "minimum": 10, "maximum": 5},
        {"type": "number", "minimum": 10, "maximum": 5},
        {"type": "number", "exclusiveMinimum": 1, "maximum": 1},
        {"type": "number", "minimum": 1, "exclusiveMaximum": 1},
    ],
)
def test_empty_or_inverted_range_raises(schema):
    with pytest.raises(ValueError, match="Cannot generate"):
        DefaultValueGenerator()(schema)()


def test_min_equals_max_is_fine():
    assert set(_samples({"type": "number", "minimum": 2, "maximum": 2})) == {2}


# ---------------------------------------------------------------------------
# multipleOf
# ---------------------------------------------------------------------------
def test_integer_multiple_of():
    schema = {"type": "integer", "minimum": 0, "maximum": 100, "multipleOf": 7}
    values = _samples(schema)
    assert all(isinstance(v, int) and v % 7 == 0 for v in values)
    assert len(set(values)) > 1
    _assert_valid(schema, values)


def test_integer_multiple_of_with_float_step():
    schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 10,
        "multipleOf": 2.5,
    }
    values = _samples(schema)
    assert all(isinstance(v, int) for v in values)
    assert set(values) <= {0, 5, 10}
    _assert_valid(schema, values)


def test_integer_with_fractional_step_draws_every_integer():
    schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 10000,
        "multipleOf": 0.001,
    }
    values = _samples(schema)
    assert all(isinstance(v, int) for v in values)
    assert len(set(values)) > 50
    _assert_valid(schema, values)


def test_multiple_of_without_bounds_uses_default_window():
    assert set(_samples({"type": "integer", "multipleOf": 25})) <= {
        0,
        25,
        50,
        75,
        100,
    }


@pytest.mark.parametrize(
    "schema, expected",
    [
        ({"type": "integer", "minimum": 99, "multipleOf": 7}, None),
        ({"type": "integer", "minimum": 1, "multipleOf": 200}, {200}),
        ({"type": "integer", "minimum": 50, "multipleOf": 1000}, {1000}),
        ({"type": "integer", "maximum": -5, "multipleOf": 7}, None),
        ({"type": "integer", "multipleOf": 1000}, {0}),
    ],
)
def test_one_sided_bound_is_widened_to_the_first_multiple(schema, expected):
    values = _samples(schema)
    if expected is not None:
        assert set(values) == expected
    _assert_valid(schema, values)


def test_number_multiple_of_passes_validator():
    schema = {"type": "number", "minimum": 0, "maximum": 1, "multipleOf": 0.01}
    values = _samples(schema)
    assert all(isinstance(v, float) for v in values)
    _assert_valid(schema, values)


def test_number_multiple_of_with_exclusive_bounds():
    schema = {
        "type": "number",
        "exclusiveMinimum": 0,
        "exclusiveMaximum": 1,
        "multipleOf": 0.25,
    }
    assert set(_samples(schema)) <= {0.25, 0.5, 0.75}


def test_number_multiple_of_tiny_open_range():
    schema = {
        "type": "number",
        "exclusiveMinimum": 0,
        "exclusiveMaximum": 0.005,
        "multipleOf": 0.001,
    }
    values = _samples(schema)
    assert set(values) <= {0.001, 0.002, 0.003, 0.004}
    _assert_valid(schema, values)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "integer", "minimum": 1, "maximum": 6, "multipleOf": 7},
        # the only candidate, 0.3, fails 0.3 / 0.1 in floating point
        {
            "type": "number",
            "exclusiveMinimum": 0.2,
            "exclusiveMaximum": 0.4,
            "multipleOf": 0.1,
        },
    ],
)
def test_multiple_of_unsatisfiable_raises(schema):
    with pytest.raises(ValueError, match="multiple of"):
        DefaultValueGenerator()(schema)()


# ---------------------------------------------------------------------------
# date-time / time formats
# ---------------------------------------------------------------------------
RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
RFC3339_TIME = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def test_date_time_has_utc_offset():
    for v in _samples({"type": "string", "format": "date-time"}, n=20):
        assert RFC3339_DATE_TIME.match(v), v


def test_time_has_utc_offset():
    for v in _samples({"type": "string", "format": "time"}, n=20):
        assert RFC3339_TIME.match(v), v


def test_date_time_fits_a_short_max_length():
    schema = {"type": "string", "format": "date-time", "maxLength": 20}
    values = _samples(schema, n=20)
    assert all(len(v) <= 20 and RFC3339_DATE_TIME.match(v) for v in values)
    _assert_valid(schema, values)


# ---------------------------------------------------------------------------
# String length with pattern / format
# ---------------------------------------------------------------------------
def test_max_length_below_default_min_length_does_not_crash():
    values = _samples({"type": "string", "maxLength": 3})
    assert all(isinstance(v, str) and len(v) <= 3 for v in values)


def test_max_length_zero():
    assert set(_samples({"type": "string", "maxLength": 0})) == {""}


def test_min_length_above_max_length_raises():
    with pytest.raises(ValueError, match="minLength=10 exceeds maxLength=3"):
        DefaultValueGenerator()(
            {"type": "string", "minLength": 10, "maxLength": 3}
        )
    with pytest.raises(ValueError, match="exceeds"):
        DefaultValueGenerator()(
            {
                "type": "string",
                "pattern": "^[a-z]+$",
                "minLength": 10,
                "maxLength": 3,
            }
        )


@pytest.mark.parametrize(
    "schema, regex, low, high",
    [
        (
            {"type": "string", "pattern": "^[a-z]+$", "maxLength": 8},
            "[a-z]+",
            0,
            8,
        ),
        (
            {"type": "string", "pattern": "^[a-z]+$", "minLength": 20},
            "[a-z]+",
            20,
            None,
        ),
        (
            {
                "type": "string",
                "pattern": "^[A-Z0-9-]+$",
                "minLength": 4,
                "maxLength": 6,
            },
            "[A-Z0-9-]+",
            4,
            6,
        ),
        (
            {"type": "string", "pattern": "^[a-z]{200,}$"},
            "[a-z]{200,}",
            200,
            None,
        ),
        (
            {"type": "string", "pattern": "^[a-z]{200,}$", "maxLength": 250},
            "[a-z]{200,}",
            200,
            250,
        ),
        (
            {"type": "string", "pattern": "^[a-z]+$", "minLength": 150},
            "[a-z]+",
            150,
            None,
        ),
        (
            {
                "type": "string",
                "pattern": "^[a-z]+-[0-9]+$",
                "minLength": 30,
                "maxLength": 40,
            },
            "[a-z]+-[0-9]+",
            30,
            40,
        ),
    ],
)
def test_pattern_with_length(schema, regex, low, high):
    values = _samples(schema, n=50)
    assert all(re.fullmatch(regex, v) for v in values)
    assert all(len(v) >= low for v in values)
    if high is not None:
        assert all(len(v) <= high for v in values)


@pytest.mark.parametrize(
    "schema, low, high",
    [
        ({"type": "string", "format": "email", "maxLength": 25}, 0, 25),
        ({"type": "string", "format": "email", "maxLength": 12}, 0, 12),
        ({"type": "string", "format": "email", "minLength": 30}, 30, None),
        ({"type": "string", "format": "email", "minLength": 300}, 300, 318),
        ({"type": "string", "format": "hostname", "minLength": 30}, 30, None),
        (
            {
                "type": "string",
                "format": "hostname",
                "minLength": 200,
                "maxLength": 253,
            },
            200,
            253,
        ),
        ({"type": "string", "format": "uri", "minLength": 60}, 60, None),
        ({"type": "string", "format": "url", "maxLength": 11}, 0, 11),
        (
            {
                "type": "string",
                "format": "phone",
                "minLength": 40,
                "maxLength": 40,
            },
            40,
            40,
        ),
    ],
)
def test_free_form_format_is_built_to_length(schema, low, high):
    values = _samples(schema, n=50)
    assert all(len(v) >= low for v in values)
    if high is not None:
        assert all(len(v) <= high for v in values)
    _assert_valid(schema, values)
    if schema["format"] == "email":
        assert all(re.fullmatch(r"[^@]+@[^@]+", v) for v in values)
    if schema["format"] in ("uri", "url"):
        assert all(re.match(r"https?://", v) for v in values)


def test_unknown_format_takes_the_plain_string_path():
    values = _samples({"type": "string", "format": "foo-bar", "maxLength": 5})
    assert all(isinstance(v, str) and len(v) <= 5 for v in values)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "format": "email", "maxLength": 2},
        {"type": "string", "format": "uuid", "maxLength": 10},
        {"type": "string", "format": "ipv4", "minLength": 20},
        {"type": "string", "format": "date", "maxLength": 5},
        {"type": "string", "pattern": "^[a-z]{10}$", "maxLength": 5},
        {"type": "string", "pattern": "^[a-z]{2,4}$", "minLength": 10},
    ],
)
def test_unsatisfiable_length_raises(schema):
    with pytest.raises(ValueError, match="Cannot generate"):
        DefaultValueGenerator()(schema)()


# ---------------------------------------------------------------------------
# _BoundedXeger relies on rstr internals: pin the contract
# ---------------------------------------------------------------------------
def test_bounded_xeger_caps_open_ended_repeats():
    xeger = _BoundedXeger(5)
    assert all(len(xeger.xeger("^[a-z]+$")) <= 5 for _ in range(300))
    assert all(len(xeger.xeger("^[a-z]*$")) <= 5 for _ in range(300))


def test_bounded_xeger_floor_raises_open_ended_repeats():
    xeger = _BoundedXeger(300, floor=200)
    assert all(200 <= len(xeger.xeger("^[a-z]+$")) <= 300 for _ in range(50))


def test_bounded_xeger_lifts_rstr_limit_for_explicit_minimum():
    # rstr alone raises "empty range" for {200,} because of STAR_PLUS_LIMIT
    assert len(_BoundedXeger(100).xeger("^[a-z]{200,}$")) == 200


def test_bounded_xeger_leaves_bounded_repeats_alone():
    xeger = _BoundedXeger(1, floor=50)
    assert all(2 <= len(xeger.xeger("^[a-z]{2,4}$")) <= 4 for _ in range(100))


# ---------------------------------------------------------------------------
# End to end: the generated sample validates against the schema
# ---------------------------------------------------------------------------
E2E_CASES = {
    "pattern+maxLength": {
        "type": "string",
        "pattern": "^[a-z]+$",
        "maxLength": 8,
    },
    "pattern+minLength": {
        "type": "string",
        "pattern": "^[a-z]+$",
        "minLength": 20,
    },
    "format+maxLength": {"type": "string", "format": "email", "maxLength": 12},
    "maxLength 3": {"type": "string", "maxLength": 3},
    "integer minimum 500": {"type": "integer", "minimum": 500},
    "integer maximum -5": {"type": "integer", "maximum": -5},
    "number minimum 10": {"type": "number", "minimum": 10},
    "integer exclusiveMinimum 200": {
        "type": "integer",
        "exclusiveMinimum": 200,
    },
    "integer boolean exclusive": {
        "type": "integer",
        "minimum": 500,
        "exclusiveMinimum": True,
    },
    "integer multipleOf 7": {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "multipleOf": 7,
    },
    "number multipleOf 0.01": {
        "type": "number",
        "minimum": 0,
        "maximum": 5,
        "multipleOf": 0.01,
    },
    "date-time": {"type": "string", "format": "date-time"},
    "time": {"type": "string", "format": "time"},
    "date": {"type": "string", "format": "date"},
    "ipv4": {"type": "string", "format": "ipv4"},
    "ipv6": {"type": "string", "format": "ipv6"},
}


def test_rfc3339_validator_is_installed_for_the_e2e_checks():
    assert "date-time" in Draft7Validator.FORMAT_CHECKER.checkers
    assert "time" in Draft7Validator.FORMAT_CHECKER.checkers


@pytest.mark.parametrize(
    "prop_schema", list(E2E_CASES.values()), ids=list(E2E_CASES)
)
def test_generated_sample_validates(prop_schema):
    schema = {
        "type": "object",
        "properties": {"v": prop_schema},
        "required": ["v"],
    }
    validator = Draft7Validator(
        schema, format_checker=Draft7Validator.FORMAT_CHECKER
    )
    gen = JSONSchemaGenerator(Schema(data=schema))
    for seed in range(30):
        random.seed(seed)
        Faker.seed(seed)
        out = gen.generate()
        errors = [e.message for e in validator.iter_errors(out)]
        assert not errors, (seed, out, errors)
