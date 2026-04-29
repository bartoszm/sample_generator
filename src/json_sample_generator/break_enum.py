"""Enumerate break sites and build break scenarios from a JSON Schema.

Three public functions mirror the structure of :mod:`scenario_enum`:

* :func:`collect_break_sites` — walk the schema and return every
  location that can be violated, together with the applicable
  :class:`~json_sample_generator.models.BreakKind` values.
* :func:`enumerate_break_scenarios` — one :class:`BreakScenario` per
  (site, kind) pair, giving full single-failure coverage.
* :func:`random_break_scenario` — ``num_failures`` randomly chosen
  (site, kind) pairs combined into a single scenario.
* :func:`merge_break_scenarios` — concatenate rules from multiple
  scenarios into one multi-break scenario.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from jsonref import JsonRef

from .helpers.allof_handler import allof_merge
from .models.break_models import BreakKind, BreakRule, BreakScenario
from .models.models import Schema

_DEFAULT_MAX_DEPTH = 6
_DEFAULT_MAX_SCENARIOS = 10_000

_KNOWN_FORMATS = {
    "email",
    "date-time",
    "date",
    "time",
    "uri",
    "url",
    "uuid",
    "hostname",
    "ipv4",
    "ipv6",
}


@dataclass(frozen=True)
class BreakSite:
    """A location in a schema where a constraint can be violated.

    Attributes:
        path: Property path (empty string at root). Array items use
            ``[*]`` as a placeholder, matching :class:`~.VariantSite`.
        schema_fragment: The schema dict at this path.
        applicable: Break kinds applicable at this site.
        required_in_parent: Whether the property at this path is listed
            in its parent's ``required`` array.
        parent_additional_props_false: Whether the parent object has
            ``additionalProperties: false``.
    """

    path: str
    schema_fragment: dict
    applicable: Tuple[BreakKind, ...]
    required_in_parent: bool = False
    parent_additional_props_false: bool = False


def collect_break_sites(
    schema: Schema, *, max_depth: int = _DEFAULT_MAX_DEPTH
) -> List[BreakSite]:
    """Walk *schema* and return every location where a break can be applied.

    The walker recurses through ``properties``, array ``items``, merged
    ``allOf`` blocks, and into each variant of ``oneOf``/``anyOf`` so
    that nested sites inside composites are also discovered.
    """
    sites: List[BreakSite] = []
    seen: Dict[str, bool] = {}
    _walk(
        schema.data,
        "",
        0,
        max_depth,
        sites,
        seen,
        required_in_parent=False,
        parent_additional_props_false=False,
    )
    return sites


def enumerate_break_scenarios(
    schema: Schema,
    *,
    name_prefix: str = "break",
    max_scenarios: int = _DEFAULT_MAX_SCENARIOS,
) -> List[BreakScenario]:
    """Return one :class:`BreakScenario` per (site, kind) pair.

    Each scenario contains a single :class:`BreakRule`, giving full
    single-failure coverage. Use :func:`merge_break_scenarios` to
    combine rules into multi-failure scenarios.

    Raises :class:`ValueError` if the total count exceeds
    ``max_scenarios``.
    """
    sites = collect_break_sites(schema)
    pairs: List[Tuple[BreakSite, BreakKind]] = [
        (site, kind) for site in sites for kind in site.applicable
    ]

    total = len(pairs)
    if total > max_scenarios:
        raise ValueError(
            f"enumerate_break_scenarios would produce {total} scenarios "
            f"(max_scenarios={max_scenarios}); raise the cap or filter "
            "sites manually."
        )

    width = max(len(str(max(total - 1, 0))), 1)
    result: List[BreakScenario] = []
    for idx, (site, kind) in enumerate(pairs):
        path = site.path
        name = f"{name_prefix}_{idx:0{width}d}"
        description = f"{kind.value} at " f"{'<root>' if not path else path!r}"
        result.append(
            BreakScenario(
                name=name,
                description=description,
                rules=[BreakRule(path=path, kind=kind)],
                expected_failure_count=1,
            )
        )
    return result


def random_break_scenario(
    schema: Schema,
    *,
    num_failures: int,
    seed: Optional[int] = None,
    name: str = "random_break",
) -> BreakScenario:
    """Return a :class:`BreakScenario` with *num_failures* random rules.

    Each rule targets a distinct break site. Uses ``random.Random(seed)``
    so results are reproducible when *seed* is provided.

    Raises :class:`ValueError` if *num_failures* exceeds the number of
    available break sites.
    """
    sites = collect_break_sites(schema)
    if num_failures > len(sites):
        raise ValueError(
            f"num_failures={num_failures} exceeds the number of "
            f"available break sites ({len(sites)})"
        )

    rng = _random.Random(seed)
    chosen = rng.sample(sites, num_failures)
    rules = [
        BreakRule(path=site.path, kind=rng.choice(list(site.applicable)))
        for site in chosen
    ]
    return BreakScenario(
        name=name,
        description=f"Random break scenario with {num_failures} failure(s)",
        rules=rules,
        expected_failure_count=num_failures,
    )


def merge_break_scenarios(
    *scenarios: BreakScenario,
    name: str,
    description: Optional[str] = None,
) -> BreakScenario:
    """Concatenate rules from multiple scenarios into one.

    Preserves rule order: rules from the first scenario come first.
    ``expected_failure_count`` is the sum of the inputs' counts when
    all inputs carry one (``None`` otherwise).
    """
    rules: List[BreakRule] = []
    total: Optional[int] = 0
    for s in scenarios:
        rules.extend(s.rules)
        if total is not None and s.expected_failure_count is not None:
            total += s.expected_failure_count
        else:
            total = None

    return BreakScenario(
        name=name,
        description=description,
        rules=rules,
        expected_failure_count=total,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _unwrap(node: Any) -> Any:
    if isinstance(node, JsonRef):
        try:
            return node.__subject__
        except Exception:
            return node
    return node


def _applicable_kinds(
    node: dict,
    required_in_parent: bool,
    parent_additional_props_false: bool,
) -> Tuple[BreakKind, ...]:
    kinds: List[BreakKind] = []

    # Nullable check: skip NULL_VALUE if the schema already allows null.
    type_val = node.get("type")
    nullable = node.get("nullable", False)
    if isinstance(type_val, list):
        nullable = nullable or "null" in type_val

    kinds.append(BreakKind.WRONG_TYPE)
    if not nullable:
        kinds.append(BreakKind.NULL_VALUE)

    if "enum" in node:
        kinds.append(BreakKind.ENUM_VIOLATION)
    if "const" in node:
        kinds.append(BreakKind.CONST_VIOLATION)
    if "pattern" in node:
        kinds.append(BreakKind.PATTERN_VIOLATION)

    typ = type_val if isinstance(type_val, str) else None
    if typ == "string":
        if "minLength" in node:
            kinds.append(BreakKind.MIN_LENGTH_VIOLATION)
        if "maxLength" in node:
            kinds.append(BreakKind.MAX_LENGTH_VIOLATION)
        fmt = node.get("format")
        if fmt in _KNOWN_FORMATS:
            kinds.append(BreakKind.FORMAT_VIOLATION)
    elif typ in ("integer", "number"):
        has_min = "minimum" in node or "exclusiveMinimum" in node
        has_max = "maximum" in node or "exclusiveMaximum" in node
        if has_min:
            kinds.append(BreakKind.MIN_VIOLATION)
        if has_max:
            kinds.append(BreakKind.MAX_VIOLATION)
    elif typ == "array":
        if "minItems" in node:
            kinds.append(BreakKind.MIN_ITEMS_VIOLATION)
        if "maxItems" in node:
            kinds.append(BreakKind.MAX_ITEMS_VIOLATION)

    if required_in_parent:
        kinds.append(BreakKind.REMOVE_REQUIRED)
    if parent_additional_props_false:
        kinds.append(BreakKind.ADDITIONAL_PROPERTY)

    return tuple(kinds)


def _walk(
    node: Any,
    path: str,
    depth: int,
    max_depth: int,
    out: List[BreakSite],
    seen: Dict[str, bool],
    required_in_parent: bool,
    parent_additional_props_false: bool,
) -> None:
    if depth > max_depth:
        return
    node = _unwrap(node)
    if not isinstance(node, dict):
        return

    # Flatten allOf before walking.
    if "allOf" in node and "oneOf" not in node and "anyOf" not in node:
        try:
            merged = allof_merge(node)
        except Exception:
            merged = node
        _walk(
            merged,
            path,
            depth + 1,
            max_depth,
            out,
            seen,
            required_in_parent,
            parent_additional_props_false,
        )
        return

    # Emit a break site for this node (if not a pure object/array wrapper).
    has_leaf_content = (
        "type" in node
        or "enum" in node
        or "const" in node
        or "pattern" in node
        or "format" in node
        or "properties" in node
        or "items" in node
    )
    if has_leaf_content and path not in seen:
        seen[path] = True
        kinds = _applicable_kinds(
            node, required_in_parent, parent_additional_props_false
        )
        if kinds:
            out.append(
                BreakSite(
                    path=path,
                    schema_fragment=dict(node),
                    applicable=kinds,
                    required_in_parent=required_in_parent,
                    parent_additional_props_false=parent_additional_props_false,
                )
            )

    # Recurse into oneOf / anyOf variants.
    for composite_key in ("oneOf", "anyOf"):
        variants = node.get(composite_key)
        if not isinstance(variants, list):
            continue
        for variant in variants:
            _walk(
                variant,
                path,
                depth + 1,
                max_depth,
                out,
                seen,
                required_in_parent,
                parent_additional_props_false,
            )

    # Recurse into properties.
    props = node.get("properties")
    required: List[str] = node.get("required") or []
    add_props = node.get("additionalProperties")
    add_props_false = add_props is False or (
        isinstance(add_props, bool) and not add_props
    )

    if isinstance(props, dict):
        for prop_name, prop_schema in props.items():
            child_path = f"{path}.{prop_name}" if path else str(prop_name)
            _walk(
                prop_schema,
                child_path,
                depth + 1,
                max_depth,
                out,
                seen,
                required_in_parent=(prop_name in required),
                parent_additional_props_false=add_props_false,
            )

    # Emit an ADDITIONAL_PROPERTY site for the parent object itself.
    if add_props_false and isinstance(props, dict) and path not in seen:
        seen[path] = True
        out.append(
            BreakSite(
                path=path,
                schema_fragment=dict(node),
                applicable=(BreakKind.ADDITIONAL_PROPERTY,),
                required_in_parent=required_in_parent,
                parent_additional_props_false=False,
            )
        )

    # Recurse into array items.
    items = node.get("items")
    if isinstance(items, (dict, JsonRef)):
        child_path = f"{path}[*]" if path else "[*]"
        _walk(
            items,
            child_path,
            depth + 1,
            max_depth,
            out,
            seen,
            required_in_parent=False,
            parent_additional_props_false=False,
        )
