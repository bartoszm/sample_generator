from __future__ import annotations

import copy
import random
import re
import warnings
from typing import Any, Callable, Dict, List, Optional, cast

from faker import Faker
from jsonref import JsonRef, jsonloader, replace_refs
from proxytypes import LazyProxy

from .DefaultValueGenerator import DefaultValueGenerator
from .helpers import allof_merge, to_type
from .helpers.utils import (
    DEFAULT_MAX_DEPTH,
    join_path,
    parse_path,
    path_startswith,
    schema_marker,
)
from .models import Context, Scenario, Schema
from .SchemaGeneratorBuilder import SchemaGeneratorBuilder

_original_lazy_subject = LazyProxy.__subject__


def _safe_lazy_subject(self):
    try:
        return object.__getattribute__(self, "cache")
    except AttributeError:
        pass
    factory = getattr(self, "factory", None)
    if callable(factory):
        cache = factory()
    else:
        try:
            cache = object.__getattribute__(self, "__wrapped__")
        except AttributeError:
            fget = getattr(_original_lazy_subject, "fget", None)
            if fget is None:
                raise AttributeError("LazyProxy.__subject__ missing fget")
            cache = fget(self)
    object.__setattr__(self, "cache", cache)
    return cache


LazyProxy.__subject__ = property(_safe_lazy_subject)

fake = Faker()

GeneratorFunctionType = Callable[[Dict[str, Any]], Callable[[], Any]]

# Redraws attempted for an array item that duplicates an earlier one when
# ``uniqueItems`` is set and the item schema has an open domain.
UNIQUE_ITEMS_ATTEMPTS = 64


def _json_key(value: Any) -> Any:
    """A hashable key under which two values are equal as JSON values:
    ``1`` and ``true`` differ, ``1`` and ``1.0`` do not."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("num", float(value))
    if isinstance(value, str):
        return ("str", value)
    if value is None:
        return ("null",)
    if isinstance(value, list):
        return ("list", tuple(_json_key(v) for v in value))
    if isinstance(value, dict):
        return (
            "dict",
            tuple(sorted((str(k), _json_key(v)) for k, v in value.items())),
        )
    return ("other", repr(value))


class JSONSchemaGenerator:
    """
    JSON schema sample data generator that creates example data based on
    JSON Schema definitions and custom scenarios.
    """

    def __init__(
        self,
        schema: Schema,
        scenario: Optional[Scenario] = None,
        allof_merger: Callable[[Dict[str, Any]], Dict[str, Any]] = allof_merge,
        max_depth: int = DEFAULT_MAX_DEPTH,
        default_value_generator: GeneratorFunctionType = DefaultValueGenerator(),
        loader=jsonloader,
        generator_max_items: Optional[int] = None,
    ):
        self.schema = Schema(
            data=cast(Dict[Any, Any], copy.deepcopy(schema.data)),
            base_uri=schema.base_uri,
        )
        self.max_depth = max_depth
        self.generator_max_items = generator_max_items

        uri = (
            self.schema.base_uri
            if self.schema.base_uri is not None
            else "file://dummy.json"
        )

        loaded = replace_refs(self.schema.data, base_uri=uri, loader=loader)
        # Ensure schema.data is a dictionary after replacing references
        if isinstance(loaded, dict):
            self.schema.data = cast(Dict[Any, Any], loaded)
        else:
            self.schema.data = cast(Dict[Any, Any], dict(cast(Any, loaded)))

        self.scenario = scenario or Scenario(name="default")
        self.default_value_generator = default_value_generator
        self.allof_merger = allof_merger

    def generate(self, scenario: Optional[Scenario] = None) -> Any:
        """
        Generate a JSON sample based on the schema and scenario.

        This method is thread-safe and can be called in parallel with different scenarios.

        Args:
            scenario: Optional scenario to use for this generation.
                     If provided, overrides the scenario set in the constructor.

        Returns:
            Generated JSON sample data
        """
        # Use the provided scenario or fall back to the default one
        active_scenario = scenario or self.scenario

        active_scenario = active_scenario.normalize()

        # Create a new builder for this generation
        builder = SchemaGeneratorBuilder()

        # Initialize result with scenario default data if provided
        if active_scenario.default_data:
            # Merge filtered default_data into builder.generated
            from .helpers.utils import deep_merge

            filtered_defaults = self._filter_default_data(
                self.schema.data, active_scenario.default_data
            )
            builder.generated = deep_merge(
                builder.generated, filtered_defaults
            )

        # Build the initial context
        ctx = builder.build_context(self.schema)

        # Start the generation process
        self._generate_node(ctx, active_scenario, builder)
        self._resolve_pending_fields(active_scenario, builder)

        return builder.get_result()

    def _filter_default_data(
        self, schema_fragment: Dict[str, Any], default_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Filter scenario default data so only known top-level properties are merged."""

        if not isinstance(default_data, dict):
            return default_data

        properties = schema_fragment.get("properties")
        if not isinstance(properties, dict):
            return {}

        return {k: v for k, v in default_data.items() if k in properties}

    def _scenario_defined(self, path: str, scenario: Scenario) -> bool:
        """
        Check if a scenario is defined for the given path.

        Args:
            path: The property path to check
            scenario: The scenario to check against

        Returns:
            True if a scenario is defined for this path
        """
        return path in scenario.overrides or any(
            pattern in path for pattern, _ in scenario.pattern_overrides
        )

    def _apply_scenario(self, ctx: Context, scenario: Scenario) -> Any:
        """
        Apply the scenario override for the given context.

        Args:
            ctx: The current generation context
            scenario: The scenario to apply

        Returns:
            The value from the scenario override

        Raises:
            ValueError: If no scenario override is defined for the path
        """
        path = ctx.prop_path
        if path in scenario.overrides:
            return scenario.overrides[path](ctx)

        for pattern, override in scenario.pattern_overrides:
            if pattern in path:
                return override(ctx)

        raise ValueError(
            f"Scenario override not defined for path: {path}. "
            "Please define a scenario for this path."
        )

    def _resolve_fragment(
        self, schema: Dict[str, Any], fragment: str
    ) -> Dict[str, Any]:
        """
        Resolve a schema fragment from a URI.

        Args:
            schema: The root schema to resolve the fragment from.
            fragment: The fragment to resolve (e.g., '#/definitions/MySchemaModel').

        Returns:
            The resolved schema fragment.

        Raises:
            KeyError: If the fragment cannot be resolved.
        """
        parts = fragment.lstrip("#/").split("/")
        for part in parts:
            if part not in schema:
                print(f"DEBUG: Current schema: {schema}")
                print(f"DEBUG: Missing part: {part}")
                raise KeyError(f"Fragment '{fragment}' not found in schema.")
            schema = schema[part]
        return schema

    def _generate_node(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ) -> Any:
        """
        Generate a node in the JSON sample based on the schema and context.

        Args:
            ctx: The current generation context
            scenario: The scenario to use for this generation
            builder: The builder instance for this generation

        Returns:
            The generated value for this node
        """
        schema = ctx.schema_data

        if self._depth(ctx.prop_path) > self.max_depth:
            self._warn_depth_cut(ctx, builder)
            return None

        if isinstance(ctx.schema_data, JsonRef):
            ref = ctx.schema_data.__reference__["$ref"]
            resolved_schema = ctx.schema_data.__subject__
            ctx = ctx.copy(
                schema_data=resolved_schema,
                schema_path=ref,
                parent_schema=resolved_schema,
                ref_path=ctx.ref_path + (ref,),
                recursive=ctx.recursive or ref in ctx.ref_path,
            )
            return self._generate_node(ctx, scenario, builder)

        path = ctx.prop_path

        if self._scenario_defined(path, scenario):
            try:
                val = self._apply_scenario(ctx, scenario)
                return builder.set_value_at_path(path, val)
            except (KeyError, IndexError):
                # The override reads data that is not generated yet
                # (ctx.data is the live result): retry in the second pass.
                builder.add_pending_field(ctx)
                return None

        if "allOf" in schema:
            return self._generate_all_of(ctx, scenario, builder)
        if "anyOf" in schema:
            return self._generate_any_of(ctx, scenario, builder)
        if "oneOf" in schema:
            return self._generate_one_of(ctx, scenario, builder)

        typ = to_type(schema)

        if typ == "object":
            return self._handle_object(ctx, scenario, builder)
        elif typ == "array":
            return self._handle_array(ctx, scenario, builder)
        else:
            # If scenario default_data already provides a value at this path, keep it
            if builder.has_value_at_path(path):
                return builder.get_value_at_path(path)
            if scenario.scenario_only:
                return None
            val = self._default_value(schema)
            return builder.set_value_at_path(path, val)

    @staticmethod
    def _depth(path: str) -> int:
        """Object nesting depth of *path*: the number of property keys
        below the root. Array indices do not add a level."""
        keys = sum(isinstance(s, str) for s in parse_path(path))
        return max(keys - 1, 0)

    def _warn_depth_cut(
        self, ctx: Context, builder: SchemaGeneratorBuilder
    ) -> None:
        """Warn once per generate() when the ``max_depth`` hard cap cuts a
        property the schema requires (or an array item needed for
        ``minItems``). Recursion normally ends through the cycle rule
        (see ``Context.recursive``); reaching the cap means the recursion
        is required all the way down, so no finite sample can validate."""
        if builder.depth_warned:
            return
        segments = parse_path(ctx.prop_path)
        parent = ctx.parent_schema
        if not segments or not hasattr(parent, "get"):
            return
        last = segments[-1]
        if isinstance(last, str):
            required = last in (parent.get("required") or [])
        else:
            required = last < (parent.get("minItems") or 0)
        if not required:
            return
        builder.depth_warned = True
        warnings.warn(
            f"max_depth={self.max_depth} reached at '{ctx.prop_path}': "
            "this required property is left out, so the sample will not "
            "validate against the schema. The schema requires its recursion "
            "all the way down, or nests deeper than the cap: pass a larger "
            "max_depth to JSONSchemaGenerator in the latter case. Further "
            "cuts in this generate() call are not reported.",
            UserWarning,
            stacklevel=2,
        )

    def _generate_all_of(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ):
        """
        Generate a node that satisfies all schemas in an allOf array.

        Args:
            ctx: The current generation context
            scenario: The scenario to use for generation
            builder: The builder instance for this generation

        Returns:
            The generated value
        """
        result = self.allof_merger(ctx.schema_data)
        # Use the original allOf schema (with potential JsonRef children) as the parent schema
        origin_parent = ctx.schema_data
        return self._generate_node(
            ctx.copy(schema_data=result, parent_schema=origin_parent),
            scenario,
            builder,
        )

    def _generate_any_of(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ):
        schemas = ctx.schema_data.get("anyOf", [])
        selected = self._resolve_variant(ctx, schemas, scenario, "anyOf")
        return self._generate_node(
            ctx.copy(schema_data=selected), scenario, builder
        )

    def _generate_one_of(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ):
        schemas = ctx.schema_data.get("oneOf", [])
        selected = self._resolve_variant(ctx, schemas, scenario, "oneOf")
        return self._generate_node(
            ctx.copy(schema_data=selected), scenario, builder
        )

    def _resolve_variant(
        self,
        ctx: Context,
        schemas: List[Dict[str, Any]],
        scenario: Scenario,
        kind: str,
    ) -> Dict[str, Any]:
        """Pick one branch from a oneOf/anyOf candidate list.

        Selector lookup in ``scenario.oneof_selectors``:
          1. exact match on ``ctx.prop_path``;
          2. else first regex (``re.fullmatch``) in insertion order.

        Selector return values:
          * ``int`` — index into ``schemas`` (``bool`` rejected).
          * ``str`` — resolved against candidate ``title``, then the
            OpenAPI discriminator value (mapping key or the const/enum/
            default of the property named by ``discriminator.propertyName``).
          * ``dict`` — taken as the selected schema fragment.
        """
        if not schemas:
            raise ValueError(
                f"{kind} has no candidates at path "
                f"'{ctx.prop_path or '<root>'}'"
            )

        selector = self._lookup_variant_selector(ctx.prop_path, scenario)
        if selector is None:
            return schemas[random.randint(0, len(schemas) - 1)]

        sel_res = selector(ctx, schemas)

        if isinstance(sel_res, bool):
            raise TypeError(
                f"{kind} selector at '{ctx.prop_path}' returned a bool; "
                "expected int, str, or dict"
            )
        if isinstance(sel_res, int):
            if sel_res < 0 or sel_res >= len(schemas):
                raise IndexError(
                    f"{kind} selector at '{ctx.prop_path}' returned "
                    f"out-of-range index {sel_res} "
                    f"(valid: 0..{len(schemas) - 1})"
                )
            return schemas[sel_res]
        if isinstance(sel_res, str):
            return self._resolve_variant_by_name(sel_res, schemas, ctx, kind)
        if isinstance(sel_res, dict):
            return sel_res

        raise TypeError(
            f"{kind} selector at '{ctx.prop_path}' returned "
            f"{type(sel_res).__name__}; expected int, str, or dict"
        )

    @staticmethod
    def _lookup_variant_selector(
        path: str, scenario: Scenario
    ) -> Optional[Callable[[Context, List[Dict[str, Any]]], Any]]:
        selectors = scenario.oneof_selectors
        if path in selectors:
            return selectors[path]
        for pattern, sel in selectors.items():
            if pattern == path:
                continue
            try:
                if re.fullmatch(pattern, path) is not None:
                    return sel
            except re.error:
                # Treat invalid regex as non-matching rather than crashing.
                continue
        return None

    @staticmethod
    def _resolve_variant_by_name(
        name: str,
        schemas: List[Dict[str, Any]],
        ctx: Context,
        kind: str,
    ) -> Dict[str, Any]:
        # 1. title match
        for s in schemas:
            if isinstance(s, dict) and s.get("title") == name:
                return s

        # 2. discriminator-based match
        disc = None
        if isinstance(ctx.schema_data, dict):
            disc = ctx.schema_data.get("discriminator")
        if disc is None and isinstance(ctx.parent_schema, dict):
            disc = ctx.parent_schema.get("discriminator")

        prop_name = None
        mapping: Dict[str, Any] = {}
        if isinstance(disc, dict):
            prop_name = disc.get("propertyName")
            mapping = disc.get("mapping") or {}

        # 2a. discriminator.mapping lookup
        target_ref = mapping.get(name)
        if target_ref is not None:
            for s in schemas:
                if not isinstance(s, dict):
                    continue
                # Schemas may still carry a $ref (jsonref inlined) — check
                # either the raw ref or a title match on the referenced name.
                if s.get("$ref") == target_ref:
                    return s
                # Fall back to matching by the last path segment of the ref.
                ref_tail = str(target_ref).rsplit("/", 1)[-1]
                if s.get("title") == ref_tail:
                    return s

        # 2b. match by the discriminator property's const/default/enum[0]
        if prop_name:
            for s in schemas:
                if not isinstance(s, dict):
                    continue
                prop = (s.get("properties") or {}).get(prop_name)
                if not isinstance(prop, dict):
                    continue
                if prop.get("const") == name:
                    return s
                if prop.get("default") == name:
                    return s
                enum = prop.get("enum")
                if isinstance(enum, list) and name in enum:
                    return s

        # Build a helpful error listing what was available.
        available_titles = [
            s.get("title")
            for s in schemas
            if isinstance(s, dict) and s.get("title")
        ]
        raise ValueError(
            f"{kind} selector at '{ctx.prop_path}' returned string "
            f"{name!r}, but no candidate matched. "
            f"Available titles: {available_titles or 'none'}; "
            f"discriminator.propertyName: {prop_name!r}; "
            f"discriminator.mapping keys: {list(mapping)}"
        )

    def _subtree_has_coverage(
        self,
        child_path: str,
        scenario: Scenario,
        builder: SchemaGeneratorBuilder,
    ) -> bool:
        """Return True if the scenario covers child_path or any descendant.

        Coverage = exact override, pattern_override that could match a
        descendant path, default_data seed, or oneof_selector entry.
        """
        for key in scenario.overrides:
            if path_startswith(child_path, key):
                return True
        for key in scenario.oneof_selectors:
            if path_startswith(child_path, key):
                return True
        if builder.has_value_at_path(child_path):
            return True
        for pat, _ in scenario.pattern_overrides:
            if pat in child_path or child_path in pat:
                return True
        return False

    def _should_include_optional(
        self,
        child_path: str,
        scenario: Scenario,
        builder: SchemaGeneratorBuilder,
    ) -> bool:
        """Return True if an optional property at *child_path* should be
        included when :attr:`Scenario.minimal_mode` is active.

        A field is included when any of the following is true:

        * An entry in ``scenario.overrides`` equals or starts with
          *child_path* (exact match or a descendant path).
        * ``scenario.default_data`` already seeded a value at *child_path*
          (checked via the builder's ``has_value_at_path``).
        * An entry in ``scenario.oneof_selectors`` equals or starts with
          *child_path*.

        ``pattern_overrides`` are intentionally excluded — they apply to
        fields that survive filtering but do not force optional fields in.
        """
        for key in scenario.overrides:
            if path_startswith(child_path, key):
                return True
        if builder.has_value_at_path(child_path):
            return True
        for key in scenario.oneof_selectors:
            if path_startswith(child_path, key):
                return True
        return False

    def _handle_array(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ) -> List[Any]:
        """
        Handle array type schema by generating array elements.

        Args:
            ctx: The current generation context
            scenario: The scenario to use for generation
            builder: The builder instance for this generation

        Returns:
            List of generated array items
        """
        schema = ctx.schema_data
        items = schema.get("items", {})

        recursive = ctx.recursive or schema_marker(schema) in ctx.ref_path
        min_items = schema.get("minItems", 0)
        if recursive:
            # The array schema recurs on the path: only the items the
            # schema insists on, so that the recursion ends.
            count = min_items
        else:
            bounds = [
                b
                for b in (schema.get("maxItems"), self.generator_max_items)
                if b is not None
            ]
            max_items = min(bounds) if bounds else max(min_items, 2)
            count = random.randint(min_items, max_items)

        # Derive schema_path for array items when items is a $ref
        item_schema_path: Optional[str] = None
        if isinstance(items, JsonRef):
            item_schema_path = items.__reference__["$ref"]

        # The root container is never an uncovered optional field, so it
        # is written even in scenario_only mode.
        if not scenario.scenario_only or not ctx.prop_path:
            builder.ensure_container(ctx.prop_path, [])

        unique = bool(schema.get("uniqueItems"))
        domain = self._unique_domain(items) if unique else None
        child_markers = ctx.ref_path + (schema_marker(schema),)
        result: List[Any] = []
        for i in range(count):
            child_ctx = ctx.copy(
                prop_path=join_path(ctx.prop_path, i),
                schema_data=items,
                parent_schema=schema,
                schema_path=item_schema_path or ctx.schema_path,
                data=builder.generated,
                ref_path=child_markers,
                recursive=recursive,
            )
            value = self._generate_node(child_ctx, scenario, builder)
            if unique:
                value = self._ensure_unique_item(
                    ctx, child_ctx, i, value, domain, scenario, builder
                )
            result.append(value)

        return result

    @staticmethod
    def _unique_domain(items: Any) -> Optional[List[Any]]:
        """The distinct values an item schema with a closed domain
        (``const``, ``enum`` or boolean) can take, else ``None``."""
        node = items.__subject__ if isinstance(items, JsonRef) else items
        if not isinstance(node, dict):
            return None
        if "const" in node:
            return [node["const"]]
        if isinstance(node.get("enum"), list):
            seen: Dict[Any, Any] = {}
            for value in node["enum"]:
                seen.setdefault(_json_key(value), value)
            return list(seen.values())
        if node.get("type") == "boolean":
            return [True, False]
        return None

    def _ensure_unique_item(
        self,
        ctx: Context,
        child_ctx: Context,
        index: int,
        value: Any,
        domain: Optional[List[Any]],
        scenario: Scenario,
        builder: SchemaGeneratorBuilder,
    ) -> Any:
        """Make the item at *index* differ, as a JSON value, from the
        earlier items of the array at ``ctx.prop_path`` (``uniqueItems``).

        A closed domain (``const``, ``enum``, boolean) is sampled without
        replacement; an open domain is redrawn up to
        :data:`UNIQUE_ITEMS_ATTEMPTS` times. An item an override chose is
        left alone. Raises ``ValueError`` when no distinct value exists.
        """
        stored = builder.get_value_at_path(ctx.prop_path)
        if not isinstance(stored, list):
            return value

        def current() -> Any:
            return stored[index] if index < len(stored) else value

        earlier = {_json_key(v) for v in stored[:index]}
        item = current()
        if item is None or _json_key(item) not in earlier:
            return item
        if self._scenario_defined(child_ctx.prop_path, scenario):
            return item

        if domain is not None:
            unused = [v for v in domain if _json_key(v) not in earlier]
            if not unused:
                raise ValueError(
                    f"uniqueItems at '{ctx.prop_path}': the item schema "
                    f"allows only {len(domain)} distinct value(s), so no "
                    f"value is left for index {index}"
                )
            chosen = copy.deepcopy(random.choice(unused))
            builder.set_value_at_path(child_ctx.prop_path, chosen)
            return chosen

        for _ in range(UNIQUE_ITEMS_ATTEMPTS):
            # Reset the slot so containers are rebuilt from scratch rather
            # than merged with the previous draw.
            builder.set_value_at_path(child_ctx.prop_path, None)
            value = self._generate_node(child_ctx, scenario, builder)
            item = current()
            if item is None or _json_key(item) not in earlier:
                return item
        raise ValueError(
            f"uniqueItems at '{ctx.prop_path}': no value distinct from the "
            f"earlier items could be drawn for index {index} in "
            f"{UNIQUE_ITEMS_ATTEMPTS} attempts"
        )

    def _handle_object(
        self, ctx: Context, scenario: Scenario, builder: SchemaGeneratorBuilder
    ) -> Dict[str, Any]:
        """
        Handle object type schema by generating properties.

        Args:
            ctx: The current generation context
            scenario: The scenario to use for generation
            builder: The builder instance for this generation

        Returns:
            Dictionary of generated property values
        """
        # The root container is never an uncovered optional field, so it
        # is written even in scenario_only mode.
        if not scenario.scenario_only or not ctx.prop_path:
            builder.ensure_container(ctx.prop_path, {})

        props = ctx.schema_data.get("properties", {})
        if props is None:
            return {}

        # The cycle rule: a schema node that recurs on the path is generated
        # with its required properties only, so that recursion ends where
        # the schema makes it optional.
        recursive = (
            ctx.recursive or schema_marker(ctx.schema_data) in ctx.ref_path
        )
        child_markers = ctx.ref_path + (schema_marker(ctx.schema_data),)
        required_set = set(ctx.schema_data.get("required") or [])
        result: Dict[str, Any] = {}

        for k, v in props.items():
            child_path = join_path(ctx.prop_path, k)
            if scenario.scenario_only:
                if not self._subtree_has_coverage(
                    child_path, scenario, builder
                ):
                    continue
            elif (
                scenario.minimal_mode or recursive
            ) and k not in required_set:
                if not self._should_include_optional(
                    child_path, scenario, builder
                ):
                    continue
            # Inherit schema_path by default; override if this property is a $ref
            child_schema_path = (
                v.__reference__["$ref"]
                if isinstance(v, JsonRef)
                else ctx.schema_path
            )

            child_ctx = ctx.copy(
                prop_path=child_path,
                schema_data=v,
                parent_schema=ctx.schema_data,
                schema_path=child_schema_path,
                data=builder.generated,
                ref_path=child_markers,
                recursive=recursive,
            )
            result[k] = self._generate_node(child_ctx, scenario, builder)

        return result

    def _default_value(self, schema: Dict[str, Any]) -> Any:
        """
        Generate a default value for a schema.

        Args:
            schema: The schema to generate a value for

        Returns:
            A generated default value
        """
        return self.default_value_generator(schema)()

    def _resolve_pending_fields(
        self, scenario: Scenario, builder: SchemaGeneratorBuilder
    ) -> None:
        """
        Attempt to resolve fields that were pending during initial generation.
        This happens when a field depends on other fields that weren't yet generated.

        Args:
            scenario: The scenario to use for resolution
            builder: The builder instance for this generation
        """
        max_retries = 5
        for _ in range(max_retries):
            if not builder.pending_fields:
                break

            still_pending = []
            for ctx in builder.pending_fields:
                try:
                    # Use a copy of the context with the latest generated data
                    updated_ctx = ctx.copy(data=builder.get_result())
                    override = self._apply_scenario(updated_ctx, scenario)
                    builder.set_value_at_path(ctx.prop_path, override)
                except (KeyError, IndexError):
                    still_pending.append(ctx)

            builder.pending_fields = still_pending
