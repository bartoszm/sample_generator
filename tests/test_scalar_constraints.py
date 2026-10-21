"""Scalar constraints in ``DefaultValueGenerator``: one-sided numeric
bounds, ``multipleOf``, RFC 3339 ``date-time``/``time`` and string length
combined with ``pattern`` or ``format``."""

from __future__ import annotations

import random
import re

import pytest
from faker import Faker
from jsonschema import Draft7Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.DefaultValueGenerator import DefaultValueGenerator
from json_sample_generator.models import Schema


def _samples(schema, n=200):
    gen = DefaultValueGenerator()(schema)
    return [gen() for _ in range(n)]


# ---------------------------------------------------------------------------
# One-sided bounds
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "schema, check",
    [
        ({"type": "integer", "minimum": 500}, lambda v: v >= 500),
        ({"type": "integer", "maximum": -5}, lambda v: v <= -5),
        ({"type": "number", "minimum": 10}, lambda v: v >= 10),
        ({"type": "number", "maximum": -2.5}, lambda v: v <= -2.5),
        ({"type": "integer", "exclusiveMinimum": 200}, lambda v: v > 200),
        ({"type": "integer", "exclusiveMaximum": -200}, lambda v: v < -200),
        ({"type": "number", "exclusiveMinimum": 10}, lambda v: v > 10),
        ({"type": "number", "exclusiveMaximum": -10}, lambda v: v < -10),
    ],
)
def test_one_sided_bound_is_respected(schema, check):
    assert all(check(v) for v in _samples(schema))


def test_one_sided_bound_inside_default_window_keeps_window():
    assert all(
        50 <= v <= 100 for v in _samples({"type": "integer", "minimum": 50})
    )
    assert all(
        0 <= v <= 5 for v in _samples({"type": "integer", "maximum": 5})
    )


def test_one_sided_bound_outside_default_window_moves_window():
    assert all(
        500 <= v <= 600 for v in _samples({"type": "integer", "minimum": 500})
    )
    assert all(
        -105 <= v <= -5 for v in _samples({"type": "integer", "maximum": -5})
    )
    assert all(
        10 <= v <= 11 for v in _samples({"type": "number", "minimum": 10})
    )


# ---------------------------------------------------------------------------
# multipleOf
# ---------------------------------------------------------------------------
def test_integer_multiple_of():
    schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "multipleOf": 7,
    }
    vals = _samples(schema)
    assert all(isinstance(v, int) for v in vals)
    assert all(v % 7 == 0 and 0 <= v <= 100 for v in vals)
    assert len(set(vals)) > 1


def test_integer_multiple_of_with_float_step():
    schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 10,
        "multipleOf": 2.5,
    }
    vals = _samples(schema)
    assert all(isinstance(v, int) for v in vals)
    assert set(vals) <= {0, 5, 10}


def test_multiple_of_without_bounds_uses_default_window():
    vals = _samples({"type": "integer", "multipleOf": 25})
    assert set(vals) <= {0, 25, 50, 75, 100}


def test_number_multiple_of_passes_validator():
    schema = {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "multipleOf": 0.01,
    }
    validator = Draft7Validator(schema)
    for v in _samples(schema):
        assert isinstance(v, float)
        assert not list(validator.iter_errors(v)), v


def test_number_multiple_of_with_exclusive_bounds():
    schema = {
        "type": "number",
        "exclusiveMinimum": 0,
        "exclusiveMaximum": 1,
        "multipleOf": 0.25,
    }
    assert set(_samples(schema)) <= {0.25, 0.5, 0.75}


def test_multiple_of_unsatisfiable_raises():
    gen = DefaultValueGenerator()(
        {"type": "integer", "minimum": 1, "maximum": 6, "multipleOf": 7}
    )
    with pytest.raises(ValueError, match="multiple of 7"):
        gen()


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


# ---------------------------------------------------------------------------
# String length with pattern / format
# ---------------------------------------------------------------------------
def test_max_length_below_default_min_length_does_not_crash():
    vals = _samples({"type": "string", "maxLength": 3})
    assert all(isinstance(v, str) and len(v) <= 3 for v in vals)


def test_max_length_zero():
    assert set(_samples({"type": "string", "maxLength": 0})) == {""}


def test_pattern_with_max_length():
    schema = {"type": "string", "pattern": "^[a-z]+$", "maxLength": 8}
    vals = _samples(schema)
    assert all(re.fullmatch("[a-z]+", v) and len(v) <= 8 for v in vals)


def test_pattern_with_min_length():
    schema = {"type": "string", "pattern": "^[a-z]+$", "minLength": 20}
    vals = _samples(schema)
    assert all(re.fullmatch("[a-z]+", v) and len(v) >= 20 for v in vals)


def test_pattern_with_both_lengths():
    schema = {
        "type": "string",
        "pattern": "^[A-Z0-9-]+$",
        "minLength": 4,
        "maxLength": 6,
    }
    vals = _samples(schema)
    assert all(re.fullmatch("[A-Z0-9-]+", v) for v in vals)
    assert all(4 <= len(v) <= 6 for v in vals)


def test_format_with_max_length():
    schema = {"type": "string", "format": "email", "maxLength": 25}
    vals = _samples(schema)
    assert all("@" in v and len(v) <= 25 for v in vals)


def test_unsatisfiable_pattern_length_warns_and_returns_candidate():
    gen = DefaultValueGenerator()(
        {"type": "string", "pattern": "^[a-z]{10}$", "maxLength": 5}
    )
    with pytest.warns(UserWarning, match="maxLength=5"):
        v = gen()
    assert re.fullmatch("[a-z]{10}", v)


def test_unsatisfiable_format_length_warns_and_returns_candidate():
    gen = DefaultValueGenerator()(
        {"type": "string", "format": "email", "maxLength": 3}
    )
    with pytest.warns(UserWarning, match="pattern/format"):
        v = gen()
    assert "@" in v


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
    "format+maxLength": {
        "type": "string",
        "format": "email",
        "maxLength": 25,
    },
    "maxLength 3": {"type": "string", "maxLength": 3},
    "integer minimum 500": {"type": "integer", "minimum": 500},
    "integer maximum -5": {"type": "integer", "maximum": -5},
    "number minimum 10": {"type": "number", "minimum": 10},
    "integer exclusiveMinimum 200": {
        "type": "integer",
        "exclusiveMinimum": 200,
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
    "ipv4": {"type": "string", "format": "ipv4"},
}


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
