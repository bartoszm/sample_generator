from __future__ import annotations

from typing import Any, List, Optional

from .helpers.utils import get_value_at_path, set_value_at_path
from .models import Context, Schema


class SchemaGeneratorBuilder:
    """
    A builder class for managing the state during JSON schema generation.
    This class provides a fluent interface for configuring and generating
    JSON samples based on schemas and scenarios.
    """

    def __init__(self):
        # The result under construction: a dict, or a list when the root
        # schema is an array.
        self.generated: Any = {}
        self.pending_fields: List[Context] = []
        self.context: Optional[Context] = None
        # Set once a max_depth warning has been emitted for this run.
        self.depth_warned: bool = False

    def build_context(self, schema: Schema, prop_path: str = "") -> Context:
        """
        Build a new context for schema generation.

        Args:
            schema: The JSON schema definition
            scenario: The scenario to apply
            prop_path: Optional property path

        Returns:
            A new Context object
        """
        return Context(
            prop_path=prop_path,
            schema_data=schema.data,
            schema_path=schema.base_uri,
            data=self.generated,
        )

    def with_context(self, context: Context) -> SchemaGeneratorBuilder:
        """
        Set the current context for generation.

        Args:
            context: The context to use

        Returns:
            Self for method chaining
        """
        self.context = context
        return self

    def set_value_at_path(self, path: str, value: Any) -> Any:
        """
        Set a value at a specific path in the generated output.

        Args:
            path: The dot-notation path
            value: The value to set

        Returns:
            The set value
        """
        if not path:
            merged = set_value_at_path(path, self.generated, value)
            if merged is self.generated:
                return merged
            if isinstance(merged, dict) and isinstance(self.generated, dict):
                # Keep the identity of the root dict: contexts created
                # earlier hold a reference to it.
                self.generated.clear()
                self.generated.update(merged)
            else:
                self.generated = merged
            return self.generated
        return set_value_at_path(path, self.generated, value)

    def ensure_container(self, path: str, container: Any) -> Any:
        """
        Write an empty *container* (``{}`` or ``[]``) at *path* unless a
        value is already there, and return the value now at *path*.

        This is what makes objects and arrays appear in the result as soon
        as the generator enters them, even when nothing is written below.
        """
        existing = self.get_value_at_path(path)
        # A root array replaces the initial {} (a dict cannot turn into a
        # list in place). The root Context built before that still holds
        # the old dict; child contexts are given builder.generated, so
        # overrides always see the live result.
        root_becomes_list = (
            not path and existing == {} and isinstance(container, list)
        )
        if existing is not None and not root_becomes_list:
            return existing
        return self.set_value_at_path(path, container)

    def add_pending_field(self, ctx: Context) -> None:
        """
        Add a field to be resolved later.

        Args:
            ctx: The context with the pending field
        """
        self.pending_fields.append(ctx)

    def get_result(self) -> Any:
        """
        Get the final generated result.

        Returns:
            The generated JSON sample
        """
        return self.generated

    # Convenience helpers for reading existing data
    def get_value_at_path(self, path: str) -> Any:
        return get_value_at_path(path, self.generated)

    def has_value_at_path(self, path: str) -> bool:
        val = self.get_value_at_path(path)
        return val is not None
