from __future__ import annotations

import json
import math
import random
import warnings
from datetime import timezone
from fractions import Fraction
from typing import Any, Callable, Dict, Optional, Tuple

import rstr
from faker import Faker

from .helpers import to_type

fake = Faker()

# Candidates drawn before giving up on a string that must satisfy
# ``minLength``/``maxLength`` together with ``pattern`` or ``format``.
STRING_ATTEMPTS = 50

# Candidate factors tried for ``multipleOf`` before giving up (a float
# step can leave no representable multiple for some factors).
MULTIPLE_ATTEMPTS = 20


class _BoundedXeger(rstr.Xeger):
    """``rstr.Xeger`` whose open-ended repeats (``+``, ``*``, ``{n,}``)
    are capped at *limit* instead of rstr's module-wide
    ``STAR_PLUS_LIMIT`` (100), so a ``pattern`` can be combined with
    ``maxLength`` without drawing hopeless candidates."""

    def __init__(self, limit: int, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._repeat_limit = limit

    def _handle_repeat(
        self, start_range: int, end_range: int, value: Any
    ) -> str:
        end_range = min(end_range, max(start_range, self._repeat_limit))
        return super()._handle_repeat(start_range, end_range, value)


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

        if "type" not in schema:
            raise ValueError(
                f"Schema {json.dumps(schema)} must contain a 'type' key."
            )

        typ = to_type(schema)
        if typ == "string":
            return self._string_generator(schema)
        if typ == "integer":
            return self._integer_generator(schema)
        if typ == "number":
            return self._number_generator(schema)
        if typ == "boolean":
            return lambda: random.choice([True, False])
        return lambda: None

    # ------------------------------------------------------------------
    # strings
    # ------------------------------------------------------------------

    def _string_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate string data honouring format, pattern and length.

        ``minLength``/``maxLength`` are applied in every branch. When they
        are combined with ``format`` or ``pattern``, candidates are drawn
        until one fits (see :data:`STRING_ATTEMPTS`); if none does, a
        ``UserWarning`` is emitted and the last candidate is returned.
        """
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")

        if "format" in schema:
            base = self._format_generator(schema["format"])
        elif "pattern" in schema:
            base = self._pattern_generator(schema["pattern"], max_length)
        elif min_length is not None or max_length is not None:
            low, high = self._length_bounds(min_length, max_length)
            return lambda: fake.pystr(min_chars=low, max_chars=high)
        else:
            return lambda: fake.word()

        if min_length is None and max_length is None:
            return base
        return lambda: self._fit_length(base, min_length, max_length, schema)

    @staticmethod
    def _length_bounds(
        min_length: Optional[int], max_length: Optional[int]
    ) -> Tuple[int, int]:
        if min_length is None:
            min_length = 5 if max_length is None else min(5, max_length)
        if max_length is None:
            max_length = min_length + 10
        return int(min_length), int(max_length)

    @staticmethod
    def _pattern_generator(
        pattern: str, max_length: Optional[int]
    ) -> Callable:
        if max_length is None:
            return lambda: rstr.xeger(pattern)
        xeger = _BoundedXeger(max(int(max_length), 1))
        return lambda: xeger.xeger(pattern)

    @staticmethod
    def _fit_length(
        base: Callable[[], str],
        min_length: Optional[int],
        max_length: Optional[int],
        schema: Dict[str, Any],
    ) -> str:
        low = 0 if min_length is None else int(min_length)
        high = math.inf if max_length is None else int(max_length)
        value = ""
        for _ in range(STRING_ATTEMPTS):
            value = base()
            if low <= len(value) <= high:
                return value
        warnings.warn(
            f"No string satisfying minLength={min_length} "
            f"maxLength={max_length} together with pattern/format was "
            f"found in {STRING_ATTEMPTS} attempts for schema "
            f"{json.dumps(schema, default=str)}; returning the last "
            "candidate, which violates the length constraint.",
            UserWarning,
        )
        return value

    # ------------------------------------------------------------------
    # numbers
    # ------------------------------------------------------------------

    def _get_value(
        self, k: str, schema: Dict[str, Any], bound_shift: float
    ) -> Optional[float]:
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
        self,
        schema: Dict[str, Any],
        bound_shift: float,
        default_low: float,
        default_high: float,
    ) -> Tuple[float, float]:
        """Return the (minimum, maximum) window to draw from.

        With a single bound the default window is kept when the bound
        falls inside it; otherwise the window is moved so that it starts
        (or ends) at the bound. Explicit bounds given the wrong way round
        are swapped, as before.
        """
        minimum = self._get_value("minimum", schema, bound_shift)
        maximum = self._get_value("maximum", schema, -bound_shift)
        low, high = float(default_low), float(default_high)
        span = high - low

        if minimum is None and maximum is None:
            return low, high
        if maximum is None:
            return minimum, (high if minimum < high else minimum + span)
        if minimum is None:
            return (low if maximum > low else maximum - span), maximum
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    @staticmethod
    def _multiple_of(schema: Dict[str, Any]) -> Optional[float]:
        value = schema.get("multipleOf")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value if value > 0 else None

    @staticmethod
    def _random_multiple(
        low: float, high: float, multiple: float, integer: bool
    ) -> Any:
        """Draw ``k * multiple`` with ``low <= k * multiple <= high``.

        Exact arithmetic picks the factor; for a float step the result is
        additionally checked the way validators do (``value / multiple``
        must be integral in floating point), retrying other factors when
        rounding noise gets in the way.
        """
        step = (
            Fraction(str(multiple))
            if isinstance(multiple, float)
            else Fraction(multiple)
        )
        k_low = math.ceil(Fraction(low) / step)
        k_high = math.floor(Fraction(high) / step)
        if k_low > k_high:
            raise ValueError(
                f"No multiple of {multiple} lies within [{low}, {high}]"
            )
        value: Any = None
        for _ in range(MULTIPLE_ATTEMPTS):
            exact = Fraction(random.randint(k_low, k_high)) * step
            if integer:
                if exact.denominator == 1:
                    return int(exact)
                continue
            value = float(exact)
            quotient = value / multiple
            if quotient == int(quotient):
                return value
        if value is None:
            raise ValueError(
                f"No integer multiple of {multiple} lies within "
                f"[{low}, {high}]"
            )
        return value

    def _integer_generator(
        self,
        schema: Dict[str, Any],
        default_low: int = 0,
        default_high: int = 100,
    ) -> Callable:
        """Generate integer data with range constraints.

        Handles missing bounds and exclusiveMinimum/exclusiveMaximum by applying
        a small integer shift and coercing bounds to integers.
        """
        minimum, maximum = self._min_max(
            schema, 1.0, default_low, default_high
        )

        low = math.ceil(minimum)
        high = math.floor(maximum)

        multiple = self._multiple_of(schema)
        if multiple is not None:
            return lambda: self._random_multiple(low, high, multiple, True)
        return lambda: random.randint(low, high)

    def _number_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate number data with range constraints."""
        minimum, maximum = self._min_max(schema, 0.01, 0.0, 1.0)
        multiple = self._multiple_of(schema)
        if multiple is not None:
            return lambda: self._random_multiple(
                minimum, maximum, multiple, False
            )
        return lambda: random.uniform(minimum, maximum)

    # ------------------------------------------------------------------
    # formats
    # ------------------------------------------------------------------

    def _format_generator(self, fmt: str) -> Callable:
        """Generate data based on format.

        ``date-time`` and ``time`` carry a UTC offset so that they are
        valid RFC 3339 values, which is what JSON Schema requires.
        """
        format_map = {
            "email": lambda: fake.email(),
            "date-time": lambda: fake.date_time_this_decade(
                tzinfo=timezone.utc
            ).isoformat(),
            "date": lambda: fake.date_this_decade().isoformat(),
            "time": lambda: f"{fake.time()}Z",
            "phone": lambda: fake.phone_number(),
            "uri": lambda: fake.uri(),
            "url": lambda: fake.url(),
            "hostname": lambda: fake.domain_name(),
            "ipv4": lambda: fake.ipv4(),
            "ipv6": lambda: fake.ipv6(),
            "uuid": lambda: fake.uuid4(),
        }
        return format_map.get(fmt, lambda: f"unknown-format-{fmt}")
