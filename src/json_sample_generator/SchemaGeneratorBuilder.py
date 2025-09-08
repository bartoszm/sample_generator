from __future__ import annotations

from typing import Any, Dict, List, Optional

from .helpers.utils import set_value_at_path, parse_path
from .models import Context, Schema


class SchemaGeneratorBuilder:
    """
    A builder class for managing the state during JSON schema generation.
    This class provides a fluent interface for configuring and generating
    JSON samples based on schemas and scenarios.
    """

    def __init__(self):
        self.generated = {}
        self.pending_fields: List[Context] = []
        self.context: Optional[Context] = None

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
        return set_value_at_path(path, self.generated, value)

    def add_pending_field(self, ctx: Context) -> None:
        """
        Add a field to be resolved later.

        Args:
            ctx: The context with the pending field
        """
        self.pending_fields.append(ctx)

    def get_result(self) -> Dict[str, Any]:
        """
        Get the final generated result.

        Returns:
            The generated JSON sample
        """
        return self.generated

    # Convenience helpers for reading existing data
    def get_value_at_path(self, path: str) -> Any:
        if not path:
            return self.generated
        ref: Any = self.generated
        try:
            for key, idx in parse_path(path):
                if not isinstance(ref, dict) or key not in ref:
                    return None
                ref = ref[key]
                if idx is not None:
                    if not isinstance(ref, list) or idx >= len(ref):
                        return None
                    ref = ref[idx]
            return ref
        except Exception:
            return None

    def has_value_at_path(self, path: str) -> bool:
        val = self.get_value_at_path(path)
        return val is not None