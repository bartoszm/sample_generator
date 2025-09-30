import json
import math
import random
from typing import Any, Callable, Dict, Optional, Tuple

import rstr
from faker import Faker

from .helpers import to_type

fake = Faker()


class DefaultValueGenerator:
    """
    A class to generate default values for various data types.
    """

    def __call__(self, schema: Dict[str, Any]) -> Callable:
        """
        Generate a default value based on the provided schema.

        :param schema: The JSON schema for which to generate a default value.
        :return: A callable that generates a default value for the specified schema.
        """

        return self._type_generator(schema)

    def _type_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate data based on type."""

        if "const" in schema:
            return lambda: schema["const"]
        if "enum" in schema:
            return lambda: random.choice(schema["enum"])

        type_map = {
            "string": self._string_generator(schema),
            "integer": self._integer_generator(schema),
            "number": self._number_generator(schema),
            "boolean": lambda: random.choice([True, False]),
            "null": lambda: None,
        }

        if "type" not in schema:
            raise ValueError(
                f"Schema {json.dumps(schema)} must contain a 'type' key."
            )

        typ = to_type(schema)
        return type_map.get(typ, lambda: None)

    def _string_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate string data with patterns and constraints."""

        if "format" in schema:
            return self._format_generator(schema["format"])

        if "pattern" in schema:
            # TODO add pattern support
            return lambda: rstr.xeger(schema["pattern"])

        if "maxLength" in schema or "minLength" in schema:
            min_length = schema.get("minLength", 5)
            max_length = schema.get("maxLength", min_length + 10)
            return lambda: fake.pystr(
                min_chars=min_length, max_chars=max_length
            )

        return lambda: fake.word()

    def _get_value(self, k: str, schema: Dict[str, Any], bound_shift: float) -> Optional[float]:
        """
        Return a numeric bound, applying bound_shift when exclusive bounds are used.

        Returns None when the key is not present or cannot be coerced to float.
        """
        ex_key = f"exclusive{k.capitalize()}"
        if ex_key in schema and schema[ex_key] is not None:
            try:
                return float(schema[ex_key]) + bound_shift
            except (TypeError, ValueError):
                return None
        if k in schema and schema[k] is not None:
            try:
                return float(schema[k])
            except (TypeError, ValueError):
                return None
        return None

    def _min_max(
        self, schema: Dict[str, Any], bound_shift: float, default_low: float, default_high: float
    ) -> Tuple[float, float]:
        minimum = self._get_value("minimum", schema, bound_shift)
        maximum = self._get_value("maximum", schema, -bound_shift)

        if minimum is None and maximum is None:
            minimum, maximum = float(default_low), float(default_high)
        elif minimum is None:
            minimum, maximum = float(default_low), float(maximum)
        elif maximum is None:
            minimum, maximum = float(minimum), float(default_high)

        # Ensure ordering
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    def _integer_generator(
        self, schema: Dict[str, Any], default_low: int = 0, default_high: int = 100
    ) -> Callable:
        """Generate integer data with range constraints.

        Handles missing bounds and exclusiveMinimum/exclusiveMaximum by applying
        a small integer shift and coercing bounds to integers.
        """
        minimum, maximum = self._min_max(schema, 1.0, default_low, default_high)

        minimum = math.ceil(minimum)
        maximum = math.floor(maximum)

        return lambda: random.randint(int(minimum), int(maximum))
        

    def _number_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate number data with range constraints."""
        minimum, maximum = self._min_max(schema, 0.01, 0.0, 1.0)
        return lambda: random.uniform(minimum, maximum)

    def _format_generator(self, fmt: str) -> Callable:
        """Generate data based on format."""
        format_map = {
            "email": lambda: fake.email(),
            "date-time": lambda: fake.date_time_this_decade().isoformat(),
            "date": lambda: fake.date_this_decade().isoformat(),
            "time": lambda: fake.time(),
            "phone": lambda: fake.phone_number(),
            "uri": lambda: fake.uri(),
            "url": lambda: fake.url(),
            "hostname": lambda: fake.domain_name(),
            "ipv4": lambda: fake.ipv4(),
            "ipv6": lambda: fake.ipv6(),
            "uuid": lambda: fake.uuid4(),
        }
        return format_map.get(fmt, lambda: f"unknown-format-{fmt}")
