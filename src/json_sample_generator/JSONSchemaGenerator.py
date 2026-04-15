from __future__ import annotations

import copy
import random
import re
from typing import Any, Callable, Dict, List, Optional, cast

from faker import Faker
from jsonref import JsonRef, jsonloader, replace_refs
from proxytypes import LazyProxy

from .DefaultValueGenerator import DefaultValueGenerator
from .helpers import allof_merge, to_type
from .helpers.utils import path_startswith
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
        max_depth: int = 6,
        default_value_generator: GeneratorFunctionType = DefaultValueGenerator(),
        loader=jsonloader,
    ):
        self.schema = Schema(
            data=cast(Dict[Any, Any], copy.deepcopy(schema.data)),
            base_uri=schema.base_uri,
        )
        self.max_depth = max_depth

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
        dpth = ctx.prop_path.count(".")
        schema = ctx.schema_data

        if dpth > self.max_depth:
            return None

        if isinstance(ctx.schema_data, JsonRef):
            ref = ctx.schema_data.__reference__["$ref"]
            resolved_schema = ctx.schema_data.__subject__
            ctx = ctx.copy(
                schema_data=resolved_schema,
                schema_path=ref,
                parent_schema=resolved_schema,
            )
            return self._generate_node(ctx, scenario, builder)

        path = ctx.prop_path

        if self._scenario_defined(path, scenario):
            try:
                val = self._apply_scenario(ctx, scenario)
                return builder.set_value_at_path(path, val)
            except KeyError:
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
            val = self._default_value(schema)
            return builder.set_value_at_path(path, val)

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

        min_items = schema.get("minItems", 0)
        max_items = schema.get("maxItems", max(min_items, 2))
        count = random.randint(min_items, max_items)

        # Derive schema_path for array items when items is a $ref
        item_schema_path: Optional[str] = None
        if isinstance(items, JsonRef):
            item_schema_path = items.__reference__["$ref"]

        result: List[Any] = []
        for i in range(count):
            child_ctx = ctx.copy(
                prop_path=f"{ctx.prop_path}[{i}]",
                schema_data=items,
                parent_schema=schema,
                schema_path=item_schema_path or ctx.schema_path,
            )
            result.append(self._generate_node(child_ctx, scenario, builder))

        return result

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
        props = ctx.schema_data.get("properties", {})
        if props is None:
            return {}

        required_set = set(ctx.schema_data.get("required") or [])
        result: Dict[str, Any] = {}

        for k, v in props.items():
            child_path = f"{ctx.prop_path}.{k}" if ctx.prop_path else k
            if scenario.minimal_mode and k not in required_set:
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
                except KeyError:
                    still_pending.append(ctx)

            builder.pending_fields = still_pending
