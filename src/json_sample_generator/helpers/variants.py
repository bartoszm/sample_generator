"""``oneOf``/``anyOf`` branches: which one a sample took, and the schema it
sees there.

Shared by the generator, which merges the keywords next to a
``oneOf``/``anyOf`` with the branch it chose (:func:`variant_siblings`),
and by :class:`~json_sample_generator.breaker.SampleBreaker`, which works
backwards from a sample (:class:`VariantResolver`).
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from .allof_handler import allof_merge
from .utils import unwrap_ref

# Keywords next to a oneOf/anyOf that do not constrain the instance and
# therefore need not be merged into the chosen branch. Vendor extensions
# (``x-...``) are treated the same way.
VARIANT_ANNOTATIONS = frozenset(
    {
        "discriminator",
        "title",
        "description",
        "$comment",
        "examples",
        "example",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "$schema",
        "$id",
        "definitions",
        "$defs",
        "components",
        "xml",
        "externalDocs",
        "nullable",
    }
)

# Steps resolve() takes at one node before it gives up: each merges an
# allOf or takes a oneOf/anyOf branch.
_MAX_RESOLVE_STEPS = 32

# Elements of an array sample compared with a candidate branch's items.
_ITEMS_COMPARED = 8

# How far below zero a branch falls when it rules out the sample.
_RULED_OUT = -1000


def variant_siblings(parent: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """The keywords of *parent* that constrain an instance together with the
    branch chosen from its *kind* (``"oneOf"`` or ``"anyOf"``): everything
    but the branch list, annotations and vendor extensions."""
    return {
        k: v
        for k, v in parent.items()
        if k != kind
        and k not in VARIANT_ANNOTATIONS
        and not k.startswith("x-")
    }


def json_type(value: Any) -> str:
    """The JSON Schema type of *value*; an integral float is an
    ``integer``."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "integer" if value.is_integer() else "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def same_value(a: Any, b: Any) -> bool:
    """*a* and *b* are the same JSON value (``1`` and ``true`` differ)."""
    return json_type(a) == json_type(b) and a == b


def accepted_types(node: Any) -> Optional[Set[str]]:
    """The JSON types *node* accepts, ``number`` standing for ``integer``
    too; ``None`` when it does not restrict them. ``type``, OpenAPI's
    ``nullable``, ``const``, ``enum``, ``allOf`` and every ``oneOf`` and
    ``anyOf`` branch count; a composition that leads back to a node being
    read counts as unrestricted."""
    known: Dict[int, Optional[Set[str]]] = {}
    reading: Set[int] = set()

    def read(node: Any) -> Optional[Set[str]]:
        node = unwrap_ref(node)
        if not isinstance(node, dict) or id(node) in reading:
            return None
        if id(node) in known:
            return known[id(node)]
        reading.add(id(node))
        try:
            accepted = _read_types(node, read)
        finally:
            reading.discard(id(node))
        known[id(node)] = accepted
        return accepted

    accepted = read(node)
    return None if accepted is None else set(accepted)


def _read_types(node: dict, read: Any) -> Optional[Set[str]]:
    """:func:`accepted_types` of one node, *read* giving its parts'."""
    accepted: Optional[Set[str]] = None

    def narrow(types: Optional[Set[str]]) -> None:
        nonlocal accepted
        if types is None:
            return
        types = set(types)
        if "number" in types:
            types.add("integer")
        accepted = types if accepted is None else accepted & types

    declared = node.get("type")
    if isinstance(declared, str):
        narrow({declared})
    elif isinstance(declared, list):
        narrow({t for t in declared if isinstance(t, str)})
    if node.get("nullable") is True and accepted is not None:
        accepted.add("null")
    if "const" in node:
        narrow({json_type(node["const"])})
    if isinstance(node.get("enum"), list):
        narrow({json_type(v) for v in node["enum"]})
    for part in node.get("allOf") or []:
        narrow(read(part))
    for composite in ("oneOf", "anyOf"):
        branches = node.get(composite)
        if not isinstance(branches, list) or not branches:
            continue
        union: Optional[Set[str]] = set()
        for branch in branches:
            types = read(branch)
            if types is None:
                union = None
                break
            union |= types
        narrow(union)
    return accepted


class _Signature:
    """What a schema says about one value: the types it accepts and the
    ``const`` or ``enum`` it holds, read once."""

    __slots__ = ("accepted", "has_const", "const", "enum")

    def __init__(self, schema: dict, flat: dict) -> None:
        accepted = accepted_types(schema)
        self.accepted: Optional[FrozenSet[str]] = (
            None if accepted is None else frozenset(accepted)
        )
        self.has_const = "const" in flat
        self.const = flat.get("const")
        enum = flat.get("enum")
        self.enum: Optional[List[Any]] = (
            enum if isinstance(enum, list) else None
        )

    def agreement(self, value: Any) -> int:
        """Strongly negative when the schema rules *value* out by its type,
        ``const`` or ``enum``; positive when its ``const`` or ``enum``
        holds *value*; else zero."""
        if self.accepted is not None and json_type(value) not in self.accepted:
            return _RULED_OUT
        if self.has_const:
            return 100 if same_value(self.const, value) else _RULED_OUT
        if self.enum is not None:
            if any(same_value(option, value) for option in self.enum):
                return 50
            return _RULED_OUT
        return 0


class _Branch:
    """A branch with its ``allOf`` merged, and what scoring a sample
    against it needs, read once."""

    __slots__ = ("sig", "required", "props", "items")

    def __init__(self, resolver: VariantResolver, flat: dict) -> None:
        self.sig = resolver.signature(flat)
        required = flat.get("required")
        self.required: List[Any] = required if required else []
        props = flat.get("properties")
        self.props: List[Tuple[Any, Any]] = (
            list(props.items()) if isinstance(props, dict) else []
        )
        items = unwrap_ref(flat.get("items"))
        self.items: Optional[dict] = items if isinstance(items, dict) else None


class VariantResolver:
    """Resolves a schema as a sample sees it, for one schema document.

    What does not depend on the sample (a branch merged, the types it
    accepts, its ``const``/``enum``) is computed once per schema node and
    kept, so resolving many paths of many samples against the same
    schema, as breaking one does, costs a scan of the sample, not a merge
    of every branch. Nodes are held while they are cached, so an ``id``
    is never reused for a different node. The schema must not be changed
    while it is in use.
    """

    def __init__(self) -> None:
        self._merged: Dict[Tuple[Any, ...], Tuple[Any, Optional[dict]]] = {}
        self._signatures: Dict[int, Tuple[Any, _Signature]] = {}
        self._branches: Dict[int, Tuple[Any, _Branch]] = {}

    # -- cached, sample-independent -------------------------------------

    def _merge(self, key: Tuple[Any, ...], parts: List[Any]) -> Optional[dict]:
        """``allOf`` of *parts*, merged; ``None`` when the merge fails.
        *key* names the parts, by identity, for the cache; *parts* (and
        so what *key* names) are kept with the result."""
        cached = self._merged.get(key)
        if cached is not None:
            return cached[1]
        try:
            merged = allof_merge({"allOf": parts})
        except Exception:
            merged = None
        result = merged if isinstance(merged, dict) else None
        self._merged[key] = (parts, result)
        return result

    def _flatten(self, node: dict) -> dict:
        """*node* with its ``allOf`` merged."""
        return self._merge((id(node),), [node]) or node

    def signature(self, schema: Any) -> Optional[_Signature]:
        """What *schema*, its ``allOf`` merged, says about a value."""
        schema = unwrap_ref(schema)
        if not isinstance(schema, dict):
            return None
        cached = self._signatures.get(id(schema))
        if cached is not None:
            return cached[1]
        flat = self._flatten(schema) if "allOf" in schema else schema
        sig = _Signature(schema, flat)
        self._signatures[id(schema)] = (schema, sig)
        return sig

    def _branch(self, variant: dict) -> _Branch:
        cached = self._branches.get(id(variant))
        if cached is not None:
            return cached[1]
        branch = _Branch(self, self._flatten(variant))
        self._branches[id(variant)] = (variant, branch)
        return branch

    # -- per sample -----------------------------------------------------

    def resolve(self, node: Any, sample: Any) -> Any:
        """*node* as *sample* sees it: ``allOf`` merged, and the ``oneOf``
        or ``anyOf`` branch the sample took chosen and merged with the
        node's own constraining keywords, the way the generator merges
        them (:func:`variant_siblings`), until neither is left."""
        for _ in range(_MAX_RESOLVE_STEPS):
            node = unwrap_ref(node)
            if not isinstance(node, dict):
                return node
            if "allOf" in node:
                merged = self._merge((id(node),), [node])
                if merged is not None and "allOf" not in merged:
                    node = merged
                    continue
            for composite in ("oneOf", "anyOf"):
                variants = node.get(composite)
                if isinstance(variants, list) and variants:
                    break
            else:
                return node
            branch = self.pick(variants, sample)
            if branch is None:
                return node
            siblings = variant_siblings(node, composite)
            if siblings:
                node = (
                    self._merge(
                        (id(node), id(branch), composite == "anyOf"),
                        [siblings, branch],
                    )
                    or branch
                )
            else:
                node = branch
        return node

    def pick(self, variants: List[Any], sample: Any) -> Optional[dict]:
        """The oneOf/anyOf variant *sample* took, each variant seen with
        its ``allOf`` merged (see :meth:`fit`). ``None`` for a value that
        is not an object when no variant accepts it."""
        best: Optional[dict] = None
        best_score: Optional[int] = None
        for v in variants:
            v = unwrap_ref(v)
            if not isinstance(v, dict):
                continue
            score = self.fit(self._branch(v), sample)
            if best_score is None or score > best_score:
                best_score = score
                best = v
        if not isinstance(sample, dict) and (best_score or 0) < 0:
            return None
        return best

    def fit(self, branch: _Branch, sample: Any, depth: int = 0) -> int:
        """How well *sample* fits *branch*: far below zero when it rules
        out its type, or a value its ``const`` or ``enum`` does not hold;
        then, for an object, the required keys and properties the sample
        has; for an array, how its first elements fit the ``items``."""
        sig = branch.sig
        score = (
            0
            if sig is None
            or sig.accepted is None
            or json_type(sample) in sig.accepted
            else _RULED_OUT
        )
        if isinstance(sample, dict):
            score += 10 * sum(1 for k in branch.required if k in sample)
            for key, prop in branch.props:
                if key in sample:
                    score += 1
                    prop_sig = self.signature(prop)
                    if prop_sig is not None:
                        score += prop_sig.agreement(sample[key])
        elif isinstance(sample, list):
            if branch.items is not None:
                items = self._branch(branch.items)
                for element in sample[:_ITEMS_COMPARED]:
                    if depth < 2:
                        score += self.fit(items, element, depth + 1)
                    elif items.sig is not None:
                        score += items.sig.agreement(element)
        elif sig is not None:
            score += sig.agreement(sample)
        return score
