import copy
import json
import re
import uuid
from typing import Any, Callable, Dict, List, Mapping, Set, Union

from jsonref import JsonRef

PathSegment = Union[str, int]

# Hard safety cap on object nesting depth. Recursion is ended by the
# cycle rule (a schema node that recurs on the current path is generated
# with only its required members); the cap only catches schemas whose
# recursion is required all the way down.
DEFAULT_MAX_DEPTH = 50

# How many times a schema node may recur on the current path. The first
# recurrence switches to required members only (the cycle rule); the next
# one is cut, with a warning when the schema requires the member. This
# keeps required recursion with several children from branching without
# bound.
MAX_REENTRIES = 2


def schema_marker(node: Any) -> Any:
    """Identity of a schema node for recursion detection: the ``$ref``
    string of a :class:`JsonRef`, else the ``id`` of the node itself (which
    also catches the reference cycles ``replace_refs(..., proxies=False)``
    produces)."""
    if isinstance(node, JsonRef):
        try:
            return node.__reference__["$ref"]
        except Exception:
            pass
    return id(node)


# One token of a property path: a dot-separated bare key, a bracketed
# index, or a bracketed JSON string for keys that contain ".", "[", "]",
# a quote or a backslash.
_TOKEN = re.compile(
    r"""
    (?P<dot>\.)?(?P<key>[^.\[\]]+)
  | \[(?P<index>\d+)\]
  | \["(?P<quoted>(?:[^"\\]|\\.)*)"\]
    """,
    re.VERBOSE,
)
_NEEDS_QUOTING = re.compile(r'[.\[\]"\\]')


def allof_ref_markers(node: Any) -> List[Any]:
    """The ``$ref`` markers of the :class:`JsonRef` parts of *node*'s
    ``allOf``, nested ``allOf`` included, in order. A merged ``allOf`` is
    a fresh dict, so these markers are what lets the recursion rule see
    through it."""
    markers: List[Any] = []
    seen: Set[int] = set()

    def visit(part: Any) -> None:
        if isinstance(part, JsonRef):
            markers.append(schema_marker(part))
            try:
                subject = part.__subject__
            except Exception:
                return
        else:
            subject = part
        if not isinstance(subject, dict) or id(subject) in seen:
            return
        seen.add(id(subject))
        for inner in subject.get("allOf") or []:
            visit(inner)

    if isinstance(node, dict):
        for part in node.get("allOf") or []:
            visit(part)
    return markers


def parse_path(path: str) -> List[PathSegment]:
    """
    Parse a property path into a flat list of keys (``str``) and
    indices (``int``).

    Syntax::

        address.city        -> ["address", "city"]
        phones[0].number    -> ["phones", 0, "number"]
        points[0][1]        -> ["points", 0, 1]      (arrays of arrays)
        [0]                 -> [0]                   (root array)
        ["a.b"].c           -> ["a.b", "c"]          (key containing ".")

    A key that contains ".", "[", "]", a quote or a backslash is written
    as a JSON string in brackets; :func:`join_path` renders paths in
    exactly this form.

    Raises:
        ValueError: if *path* does not follow the syntax above.
    """
    if path == "":
        return []
    segments: List[PathSegment] = []
    pos = 0
    while pos < len(path):
        match = _TOKEN.match(path, pos)
        if match is None:
            raise ValueError(f"Invalid path: {path!r} (at offset {pos})")
        key, index, quoted = match.group("key", "index", "quoted")
        if key is not None:
            if bool(match.group("dot")) != (pos > 0):
                raise ValueError(f"Invalid path: {path!r} (at offset {pos})")
            segments.append(key)
        elif index is not None:
            segments.append(int(index))
        else:
            try:
                segments.append(json.loads(f'"{quoted}"'))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid path: {path!r} (bad escape in quoted key)"
                ) from exc
        pos = match.end()
    return segments


def join_path(parent: str, segment: PathSegment) -> str:
    """Append *segment* (a key or an index) to *parent* using the syntax
    understood by :func:`parse_path`.

    Keys that contain ".", "[", "]", a quote or a backslash, and the
    empty key, are rendered as a bracketed JSON string.
    """
    if isinstance(segment, bool) or not isinstance(segment, (int, str)):
        raise TypeError(
            f"path segment must be str or int, got {type(segment).__name__}"
        )
    if isinstance(segment, int):
        return f"{parent}[{segment}]"
    if segment == "" or _NEEDS_QUOTING.search(segment):
        return f"{parent}[{json.dumps(segment, ensure_ascii=False)}]"
    return f"{parent}.{segment}" if parent else segment


def path_startswith(prefix: str, path: str) -> bool:
    """Return True if *path* is equal to *prefix* or begins with it.

    Uses the dot/bracket conventions of :func:`parse_path` so that a prefix
    of ``"foo"`` matches ``"foo"``, ``"foo.bar"``, and ``"foo[0]"`` but not
    ``"foobar"``.
    """
    if path == prefix:
        return True
    return path.startswith(prefix + ".") or path.startswith(prefix + "[")


def deep_merge(a: dict, b: dict) -> dict:
    result = copy.deepcopy(a)
    for k, v in b.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            # Preserve JsonRef wrappers to keep $ref metadata for later tracing
            if isinstance(v, JsonRef):
                result[k] = v
            else:
                result[k] = copy.deepcopy(v)
    return result


def remove_nulls(obj: Any) -> Any:
    """
    Remove all null values from a nested structure (dicts and lists).
    """
    if isinstance(obj, dict):
        cleaned_dict = {}
        for k, v in obj.items():
            cleaned_value = remove_nulls(v)
            if cleaned_value is not None:
                cleaned_dict[k] = cleaned_value
        return cleaned_dict
    elif isinstance(obj, list):
        cleaned_list = [remove_nulls(i) for i in obj if i is not None]
        return cleaned_list if cleaned_list else None
    return obj


def _container_for(segment: PathSegment) -> Any:
    """Return the empty container that can hold *segment* as its child."""
    return [] if isinstance(segment, int) else {}


def _pad_list(target: list, index: int, factory: Callable[[], Any]) -> None:
    while len(target) <= index:
        target.append(factory())


def _descend(ref: Any, segment: PathSegment, next_segment: PathSegment) -> Any:
    """Return the child container at *segment* of *ref*, creating it if
    it is missing or ``None``."""
    if isinstance(segment, int):
        if not isinstance(ref, list):
            raise TypeError(
                f"Cannot index a {type(ref).__name__} with [{segment}]"
            )
        _pad_list(ref, segment, lambda: _container_for(next_segment))
        if ref[segment] is None:
            ref[segment] = _container_for(next_segment)
        return ref[segment]
    if not isinstance(ref, dict):
        raise TypeError(
            f"Cannot access key {segment!r} on a {type(ref).__name__}"
        )
    if ref.get(segment) is None:
        ref[segment] = _container_for(next_segment)
    return ref[segment]


def set_value_at_path(
    path: str, target: Any, value: Any, force: bool = True
) -> Any:
    """
    Set a value at a specified path in a nested dictionary or list.
    Missing containers along the path are created: a dict when the next
    segment is a key, a list when it is an index. Lists are padded as
    needed.

    With an empty *path* the value is merged into *target* when both are
    dicts, otherwise it replaces it; the result is returned and callers
    must use it, since a dict cannot be turned into a list in place.

    Args:
        path (str): The path where the value should be set.
        target (Any): The target object (dict or list) to modify.
        value (Any): The value to set at the specified path.
        force (bool): Overwrite an existing value (default). When False
            an existing value is kept and returned.
    Returns:
        Any: The value now stored at *path* (the merged root for an
        empty path).
    """
    segments = parse_path(path)
    if not segments:
        if isinstance(target, dict) and isinstance(value, dict):
            return deep_merge(target, value)
        return value

    ref = target
    for pos, segment in enumerate(segments[:-1]):
        ref = _descend(ref, segment, segments[pos + 1])

    last = segments[-1]
    if isinstance(last, int):
        if not isinstance(ref, list):
            raise TypeError(
                f"Cannot index a {type(ref).__name__} with [{last}]"
            )
        _pad_list(ref, last, lambda: None)
        if force or ref[last] is None:
            ref[last] = value
        return ref[last]
    if not isinstance(ref, dict):
        raise TypeError(
            f"Cannot access key {last!r} on a {type(ref).__name__}"
        )
    if force or last not in ref:
        ref[last] = value
    return ref[last]


def get_value_at_path(path: str, target: Any) -> Any:
    """Return the value at *path* in *target*, or ``None`` if not found."""
    try:
        ref: Any = target
        for segment in parse_path(path):
            if isinstance(segment, int):
                if not isinstance(ref, list) or segment >= len(ref):
                    return None
            elif not isinstance(ref, dict) or segment not in ref:
                return None
            ref = ref[segment]
        return ref
    except Exception:
        return None


def delete_value_at_path(path: str, target: Any) -> bool:
    """Delete the value at *path* from *target*.

    Returns ``True`` if the key existed and was deleted, ``False`` if
    the path did not exist.
    """
    segments = parse_path(path)
    if not segments:
        return False

    ref: Any = target
    for segment in segments[:-1]:
        if isinstance(segment, int):
            if not isinstance(ref, list) or segment >= len(ref):
                return False
        elif not isinstance(ref, dict) or segment not in ref:
            return False
        ref = ref[segment]

    last = segments[-1]
    if isinstance(last, int):
        if not isinstance(ref, list) or last >= len(ref):
            return False
        del ref[last]
        return True
    if not isinstance(ref, dict) or last not in ref:
        return False
    del ref[last]
    return True


def sort_with_priority(
    data: Mapping[str, Any],
    priority: List[str] = ["@type", "@baseType", "id", "href"],
):
    def sort_w_p(lst):
        priority_set = set(priority)
        priority_part = [x for x in priority if x in lst]
        rest_part = sorted(x for x in lst if x not in priority_set)
        return priority_part + rest_part

    if isinstance(data, list):
        return [sort_with_priority(item, priority) for item in data]

    if not isinstance(data, dict):
        return data
    sorted_keys = sort_w_p(data.keys())
    return {k: sort_with_priority(data[k], priority) for k in sorted_keys}


CUSTOM_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def duuid(*seeds: Any) -> uuid.UUID:
    seed_string = "".join(str(seeds))
    return uuid.uuid5(CUSTOM_NAMESPACE, seed_string)


def to_type(schema: Dict[str, Any]) -> str:
    """
    Convert a schema to its type representation.

    Args:
        schema: The schema to convert

    Returns:
        The type as a string
    """
    base_types = {
        "object",
        "array",
        "string",
        "number",
        "integer",
        "boolean",
        "null",
    }

    def _multitype(t: str) -> str:
        if isinstance(t, list):
            return next((x for x in t if x in base_types), t[0])
        return t

    if "type" in schema:
        return _multitype(schema["type"])
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return "null"
