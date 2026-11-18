"""Apply break scenarios to valid samples, producing invalid ones.

Public surface:

* :class:`SampleBreaker` — stateful breaker bound to a :class:`~.Schema`.
* :func:`apply_break_scenario` — functional shortcut for one-off use.

The engine operates on a **deep copy** of the input sample — the
original is never modified.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from .DefaultValueGenerator import DefaultValueGenerator
from .helpers.utils import (
    delete_value_at_path,
    get_value_at_path,
    parse_path,
    set_value_at_path,
    to_type,
    unwrap_ref,
)
from .helpers.variants import VariantResolver, accepted_types
from .models.break_models import BreakKind, BreakRule, BreakScenario
from .models.models import Schema

_dvg = DefaultValueGenerator()

_WRONG_TYPE_CANDIDATES = [
    "string",
    "integer",
    "number",
    "boolean",
    "array",
    "object",
    "null",
]

# No sample value at the path (as opposed to a JSON null).
_NO_VALUE = object()

# The value written for a wrong type that the value generator has no
# default for.
_WRONG_TYPE_VALUES: Dict[str, Any] = {"array": [], "object": {}, "null": None}

_FORMAT_INVALID: Dict[str, str] = {
    "email": "not-an-email",
    "date-time": "not-a-datetime",
    "date": "not-a-date",
    "time": "not-a-time",
    "uri": "not a uri",
    "url": "not a url",
    "uuid": "not-a-uuid",
    "hostname": "not a hostname!",
    "ipv4": "999.999.999.999",
    "ipv6": "gggg::1",
}


def apply_break_scenario(
    schema: Schema,
    sample: dict,
    scenario: BreakScenario,
) -> dict:
    """Apply *scenario* to *sample* and return the mutated copy.

    Shortcut for ``SampleBreaker(schema).apply(sample, scenario)``.
    """
    return SampleBreaker(schema).apply(sample, scenario)


class SampleBreaker:
    """Applies :class:`~.BreakScenario` mutations to a valid sample.

    Parameters
    ----------
    schema:
        The JSON Schema that the input samples conform to.
    """

    def __init__(self, schema: Schema) -> None:
        self._schema = schema
        self._variants = VariantResolver()

    def apply(self, sample: dict, scenario: BreakScenario) -> dict:
        """Return a deep copy of *sample* with all *scenario* rules applied."""
        result = copy.deepcopy(sample)
        for rule in scenario.rules:
            self._apply_rule(result, rule)
        return result

    # ------------------------------------------------------------------
    # Rule dispatch
    # ------------------------------------------------------------------

    def _apply_rule(self, data: dict, rule: BreakRule) -> None:
        if rule.value is not None:
            set_value_at_path(rule.path, data, rule.value)
            return

        kind = rule.kind

        # For kinds that mutate an existing value, skip rules whose path
        # does not exist in the sample (e.g. a oneOf branch not taken).
        # ADDITIONAL_PROPERTY is exempt — it adds a new key to the parent.
        if kind != BreakKind.ADDITIONAL_PROPERTY and rule.path:
            existing = get_value_at_path(rule.path, data)
            if existing is None and not _path_exists(data, rule.path):
                return

        node, value = self._locate(data, rule.path)
        frag = self._variants.resolve(node, value)
        if not isinstance(frag, dict):
            frag = {}

        if kind == BreakKind.REMOVE_REQUIRED:
            delete_value_at_path(rule.path, data)

        elif kind == BreakKind.NULL_VALUE:
            set_value_at_path(rule.path, data, None)

        elif kind == BreakKind.WRONG_TYPE:
            invalid = self._wrong_type_value(node, frag)
            set_value_at_path(rule.path, data, invalid)

        elif kind == BreakKind.ENUM_VIOLATION:
            invalid = self._enum_violation(frag)
            set_value_at_path(rule.path, data, invalid)

        elif kind == BreakKind.CONST_VIOLATION:
            invalid = self._const_violation(frag)
            set_value_at_path(rule.path, data, invalid)

        elif kind == BreakKind.PATTERN_VIOLATION:
            current = get_value_at_path(rule.path, data) or ""
            set_value_at_path(rule.path, data, "!!!" + str(current))

        elif kind == BreakKind.MIN_LENGTH_VIOLATION:
            min_len = frag.get("minLength", 1)
            truncated = "" if min_len <= 1 else "x" * (min_len - 1)
            set_value_at_path(rule.path, data, truncated)

        elif kind == BreakKind.MAX_LENGTH_VIOLATION:
            max_len = frag.get("maxLength", 0)
            set_value_at_path(rule.path, data, "x" * (max_len + 1))

        elif kind == BreakKind.MIN_VIOLATION:
            bound = _get_numeric_bound(frag, "min")
            if bound is not None:
                set_value_at_path(rule.path, data, bound - 1)

        elif kind == BreakKind.MAX_VIOLATION:
            bound = _get_numeric_bound(frag, "max")
            if bound is not None:
                set_value_at_path(rule.path, data, bound + 1)

        elif kind == BreakKind.ADDITIONAL_PROPERTY:
            target = _resolve_dict_at(data, rule.path)
            if isinstance(target, dict):
                target["__break_extra__"] = "unexpected"

        elif kind == BreakKind.MIN_ITEMS_VIOLATION:
            min_items = frag.get("minItems", 1)
            current = get_value_at_path(rule.path, data)
            if isinstance(current, list):
                sliced = current[: max(min_items - 1, 0)]
                set_value_at_path(rule.path, data, sliced)

        elif kind == BreakKind.MAX_ITEMS_VIOLATION:
            max_items = frag.get("maxItems", 0)
            current = get_value_at_path(rule.path, data)
            if isinstance(current, list) and current:
                padded = list(current) + [current[-1]] * (
                    max_items + 1 - len(current)
                )
                set_value_at_path(rule.path, data, padded)
            elif isinstance(current, list):
                set_value_at_path(
                    rule.path, data, ["__break__"] * (max_items + 1)
                )

        elif kind == BreakKind.FORMAT_VIOLATION:
            fmt = frag.get("format", "")
            invalid = _FORMAT_INVALID.get(fmt, f"not-a-{fmt}")
            set_value_at_path(rule.path, data, invalid)

    # ------------------------------------------------------------------
    # Schema resolution helpers
    # ------------------------------------------------------------------

    def _resolve_schema(self, data: dict, path: str) -> dict:
        """Walk *path* in both *data* and the schema, returning the schema
        fragment, with ``allOf`` merged and the ``oneOf``/``anyOf`` branch
        the sample took chosen at every level (see
        :meth:`.VariantResolver.resolve`)."""
        node, value = self._locate(data, path)
        frag = self._variants.resolve(node, value)
        return frag if isinstance(frag, dict) else {}

    def _locate(self, data: Any, path: str) -> Tuple[Any, Any]:
        """The schema node at *path*, its own composition not resolved
        yet, and the sample value there. When the path leaves the sample,
        the node and value of the last level present."""
        node: Any = self._schema.data
        current: Any = data
        for segment in parse_path(path) if path else []:
            node = self._variants.resolve(node, current)
            if not isinstance(node, dict):
                return {}, _NO_VALUE
            if (
                isinstance(segment, str)
                and isinstance(current, dict)
                and segment in current
            ):
                props = node.get("properties")
                node = (
                    props.get(segment, {}) if isinstance(props, dict) else {}
                )
                current = current[segment]
            elif (
                isinstance(segment, int)
                and isinstance(current, list)
                and 0 <= segment < len(current)
            ):
                node = node.get("items", {})
                current = current[segment]
            else:
                # Path not found in data — return schema node as-is.
                break
        return unwrap_ref(node), current

    # ------------------------------------------------------------------
    # Value generators
    # ------------------------------------------------------------------

    def _wrong_type_value(self, node: Any, frag: dict) -> Any:
        """A value of a type the schema *node* does not accept: every
        ``oneOf`` and ``anyOf`` branch counts, and ``integer`` is a
        ``number``. A schema that does not restrict the type has no wrong
        type; it gets what it always got, a value of a type other than
        ``to_type`` of the resolved fragment *frag* (a string for an
        untyped ``pattern``, which a string can still break)."""
        accepted = accepted_types(node)
        if accepted:
            if "number" in accepted:
                accepted.add("integer")
            candidates = [
                c for c in _WRONG_TYPE_CANDIDATES if c not in accepted
            ]
        else:
            current = to_type(frag)
            candidates = [c for c in _WRONG_TYPE_CANDIDATES if c != current]
        for candidate in candidates:
            if candidate in _WRONG_TYPE_VALUES:
                return copy.deepcopy(_WRONG_TYPE_VALUES[candidate])
            try:
                return _dvg({"type": candidate})()
            except Exception:
                continue
        return "WRONG_TYPE_FALLBACK"

    def _enum_violation(self, frag: dict) -> Any:
        enum_vals = frag.get("enum", [])
        sentinel = "__break_not_in_enum__"
        if sentinel not in enum_vals:
            return sentinel
        # Append a suffix to escape the enum exhaustively.
        return str(sentinel) + "_X"

    def _const_violation(self, frag: dict) -> Any:
        const = frag.get("const")
        if isinstance(const, str):
            return const + "_X"
        if isinstance(const, bool):
            return not const
        if isinstance(const, (int, float)):
            return const + 1
        return "__break_const__"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _get_numeric_bound(frag: dict, direction: str) -> Optional[float]:
    """Return the inclusive bound for *direction* (``"min"`` or ``"max"``)."""
    if direction == "min":
        if "exclusiveMinimum" in frag:
            return float(frag["exclusiveMinimum"])
        if "minimum" in frag:
            return float(frag["minimum"])
    elif direction == "max":
        if "exclusiveMaximum" in frag:
            return float(frag["exclusiveMaximum"])
        if "maximum" in frag:
            return float(frag["maximum"])
    return None


def _resolve_dict_at(data: dict, path: str) -> Any:
    """Return the dict/list at *path*, or the root dict when *path* is empty."""
    if not path:
        return data
    return get_value_at_path(path, data)


def _path_exists(data: Any, path: str) -> bool:
    """Return True when *path* navigates to an existing key in *data*."""
    if not path:
        return True
    ref = data
    for segment in parse_path(path):
        if isinstance(segment, int):
            if not isinstance(ref, list) or segment >= len(ref):
                return False
        elif not isinstance(ref, dict) or segment not in ref:
            return False
        ref = ref[segment]
    return True
