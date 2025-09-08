import json
import random
from typing import Any, Callable, Dict

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

    def _integer_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate integer data with range constraints."""
        minimum = schema.get("minimum", -100)
        maximum = schema.get("maximum", 100)

        if schema.get("exclusiveMinimum"):
            minimum += 1
        if schema.get("exclusiveMaximum"):
            maximum -= 1

        return lambda: random.randint(minimum, maximum)

    def _number_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate number data with range constraints."""
        minimum = schema.get("minimum", -100.0)
        maximum = schema.get("maximum", 100.0)

        if schema.get("exclusiveMinimum"):
            minimum += 0.01
        if schema.get("exclusiveMaximum"):
            maximum -= 0.01

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
