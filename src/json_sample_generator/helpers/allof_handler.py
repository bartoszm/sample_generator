from typing import Any, Dict, List, Optional, Set

from jsonref import JsonRef


def allof_merge(
    ctx: Dict[str, Any], visited: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Shallowly merge a schema with allOf by traversing and flattening parent
    chains (including nested allOf and $ref). Later entries override earlier
    ones at the top level. 'properties' is merged by shallow key union; 'required'
    lists are unioned while preserving order. JsonRef instances within property
    values are preserved (no deep copying).

    Deduplication:
    - Repeated $ref parents are merged only once (by $ref string).
    - Direct dict instances are cycle-protected by object id.
    """
    # Unwrap if the ctx itself is a reference (to see allOf)
    root: Any = ctx.__subject__ if isinstance(ctx, JsonRef) else ctx

    if not isinstance(root, dict) or "allOf" not in root:
        # Nothing to merge; return as-is
        return root

    seen_refs: Set[str] = set(visited or set())
    seen_ids: Set[int] = set()

    def ref_key(node: Any) -> Optional[str]:
        if isinstance(node, JsonRef):
            try:
                ref = node.__reference__.get("$ref")
                return str(ref) if ref is not None else None
            except Exception:
                return None
        return None

    def flatten_allof(node: Any) -> List[Dict[str, Any]]:
        # Resolve references
        if isinstance(node, JsonRef):
            rk = ref_key(node)
            if rk is not None:
                if rk in seen_refs:
                    return []
                seen_refs.add(rk)
            node = node.__subject__

        if not isinstance(node, dict):
            return []

        # Cycle guard for inline dicts
        obj_id = id(node)
        if obj_id in seen_ids:
            return []
        seen_ids.add(obj_id)

        parts: List[Dict[str, Any]] = []

        if "allOf" in node and isinstance(node["allOf"], list):
            for part in node["allOf"]:
                parts.extend(flatten_allof(part))

            # Siblings alongside allOf should be applied after its parents
            siblings = {k: v for k, v in node.items() if k != "allOf"}
            if siblings:
                parts.append(siblings)  # shallow dict; values are preserved
        else:
            parts.append(node)

        return parts

    def merge_required(dst: Dict[str, Any], incoming: Any) -> None:
        if incoming is None:
            return
        inc_list = list(incoming) if isinstance(incoming, list) else []
        cur = (
            list(dst.get("required", []))
            if isinstance(dst.get("required"), list)
            else []
        )
        # Deduplicate preserving order
        merged: List[Any] = []
        for x in cur + inc_list:
            if x not in merged:
                merged.append(x)
        if merged:
            dst["required"] = merged

    def merge_shallow(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
        for k, v in src.items():
            if k == "properties":
                dst_props = dst.setdefault("properties", {})
                if isinstance(dst_props, dict) and isinstance(v, dict):
                    for pk, pv in v.items():
                        # override by last; preserve JsonRef wrappers
                        dst_props[pk] = pv
                else:
                    # Replace if shapes differ
                    dst["properties"] = v
            elif k == "required":
                merge_required(dst, v)
            elif k == "allOf":
                # ignore here; handled by flatten_allof
                continue
            else:
                # Top-level override by last occurrence
                dst[k] = v

    # Flatten all parents across nested allOf/refs
    chain = flatten_allof(root)

    # Merge in order
    result: Dict[str, Any] = {}
    for part in chain:
        merge_shallow(result, part)

    return result
