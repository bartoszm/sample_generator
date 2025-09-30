import copy
import re
import uuid
from typing import Any, Dict, List, Optional, Mapping

from jsonref import JsonRef

pattern = re.compile(r"^([^\\\[\]]+)(?:\[(\d+)\])?$")


def _to_idx(s: str) -> Optional[int]:
    try:
        return int(s)
    except TypeError:
        return None


def parse_path(path: str):
    """
    Parse a JSON path string into a list of keys and indices.

    Args:
        path (str): The JSON path string to parse.

    Returns:
        list: A list of keys and indices representing the path.
    """
    keys = []
    for part in path.split("."):
        match = pattern.match(part)
        if match:
            key, index = match.groups()
            keys.append((key, _to_idx(index)))
        else:
            raise ValueError(f"Invalid path segment: {part}")
    return keys


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
    Remove all null values from a nested structure.
    """
    if isinstance(obj, dict):
        return {k: remove_nulls(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [remove_nulls(i) for i in obj if i is not None]
    else:
        return obj


def set_value_at_path(path: str, target: Any, value: Any, force: bool = True) -> Any:
    """
    Set a value at a specified path in a nested dictionary or list.
    If the path does not exist, it will be created.
    Args:
        path (str): The path where the value should be set.
        target (Any): The target object (dict or list) to modify.
        value (Any): The value to set at the specified path.
    Returns:
        Any: The modified target object.
    """

    def set_value(target, key, value):
        if force or key not in target:
            target[key] = value
            return value
        return target[key]

    def initiate_if_not_exists(
        target: Any, key: str, idx: Optional[int] = None
    ) -> Any:
        if key not in target:
            if idx is None:
                target[key] = {}
            else:
                target[key] = []
        if idx is not None and idx >= len(target[key]):
            target[key].extend([{} for _ in range(idx - len(target[key]) + 1)])

    if not path or path == "":
        target = deep_merge(target, value)
        return target

    keys = parse_path(path)

    ref = target
    for key, idx in keys[:-1]:
        initiate_if_not_exists(ref, key, idx)

        if idx is not None:
            ref = ref[key][idx]
        else:
            ref = ref[key]

    key, idx = keys[-1]

    initiate_if_not_exists(ref, key, idx)

    if idx is not None:
        return set_value(ref[key], idx, value)
    else:
        return set_value(ref, key, value)


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
