from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BreakKind(str, Enum):
    """Ways a sample can be made to violate a JSON Schema constraint."""

    WRONG_TYPE = "wrong_type"
    REMOVE_REQUIRED = "remove_required"
    NULL_VALUE = "null_value"
    ENUM_VIOLATION = "enum_violation"
    CONST_VIOLATION = "const_violation"
    PATTERN_VIOLATION = "pattern_violation"
    MIN_LENGTH_VIOLATION = "min_length_violation"
    MAX_LENGTH_VIOLATION = "max_length_violation"
    MIN_VIOLATION = "min_violation"
    MAX_VIOLATION = "max_violation"
    ADDITIONAL_PROPERTY = "additional_property"
    MIN_ITEMS_VIOLATION = "min_items_violation"
    MAX_ITEMS_VIOLATION = "max_items_violation"
    FORMAT_VIOLATION = "format_violation"


class BreakRule(BaseModel):
    """A single mutation to apply to a generated sample.

    ``path`` uses the same dot/bracket grammar as ``Scenario.overrides``
    (e.g. ``"address.city"`` or ``"items[0].name"``).
    ``value``, when set, overrides the auto-derived invalid value.
    """

    path: str
    kind: BreakKind
    value: Any = None
    note: str | None = None


class BreakScenario(BaseModel):
    """A named set of break rules to apply to a valid sample."""

    name: str
    description: str | None = None
    rules: list[BreakRule] = Field(default_factory=list)
    expected_failure_count: int | None = None
