# scenario.py
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

from jsonref import jsonloader, replace_refs
from pydantic import BaseModel, Field

# Define a type for scenario override functions
ScenarioOverrideFn = Callable[["Context"], Any]

# Define a type for scenario override values (can be a function or a direct value)
ScenarioOverrideValue = Union[ScenarioOverrideFn, Any]


class Scenario(BaseModel):
    name: str
    description: Optional[str] = None
    overrides: Dict[str, Any] = Field(
        default_factory=dict
    )  # Allow any value type
    pattern_overrides: List[Tuple[str, Any]] = Field(
        default_factory=list
    )  # Allow any value type
    # Default data used to initialize the generated result
    default_data: Dict[str, Any] = Field(default_factory=dict)

    def normalize(self) -> "Scenario":
        """
        Convert any non-function overrides to lambda functions automatically.
        This allows users to specify simple values directly without writing lambdas.
        """
        # Process regular overrides
        converted_overrides = {}
        for key, value in self.overrides.items():
            if callable(value):
                # Keep function as is
                converted_overrides[key] = value
            else:
                # Convert direct value to a lambda function that returns the value
                direct_value = value  # Capture the value in a closure
                converted_overrides[key] = lambda ctx, val=direct_value: val

        # Process pattern overrides
        converted_pattern_overrides = []
        for pattern, value in self.pattern_overrides:
            if callable(value):
                # Keep function as is
                converted_pattern_overrides.append((pattern, value))
            else:
                # Convert direct value to a lambda function that returns the value
                direct_value = value  # Capture the value in a closure
                converted_pattern_overrides.append(
                    (pattern, lambda ctx, val=direct_value: val)
                )

        # Update the scenario with converted values
        self.overrides = converted_overrides
        self.pattern_overrides = converted_pattern_overrides

        return self


class Schema(BaseModel):
    data: Dict[Any, Any]
    base_uri: Optional[str] = None

    @staticmethod
    def from_raw_data(raw: Dict[str, Any], base_uri: str) -> Schema:
        """
        Create a Schema instance from raw data.
        This is useful for creating schemas without needing to load from a file.
        """

        data = cast(
            Dict[Any, Any],
            replace_refs(raw, base_uri=base_uri, loader=jsonloader),
        )

        if "#" in base_uri:
            # If base_uri contains a fragment, remove it for consistency
            fragment = base_uri.split("#")[1]

            # Navigate to the fragment path in the data
            fragment_parts = fragment.split("/")
            current_data = data
            for part in fragment_parts:
                if part and part in current_data:
                    current_data = current_data[part]
                elif part:
                    raise ValueError(
                        f"Fragment '{fragment}' not found in schema data."
                    )
            data = current_data

        return Schema(data=data, base_uri=base_uri)


class Context(BaseModel):
    prop_path: str
    data: Dict[str, Any]
    schema_data: Dict[str, Any]
    schema_path: Optional[str] = None
    parent_schema: Optional[Dict[str, Any]] = None
    parent_ctx: Optional["Context"] = None

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def copy(self, **updates) -> "Context":
        """
        Shallow clone with optional field overrides:
            new_rec = rec.copy(path="new.json", data={**rec.data, "x": 1})
        """
        return self.model_copy(update=updates)

    class Config:
        validate_assignment = True
        extra = "forbid"
