from __future__ import annotations

import json
import math
import random
import string
from datetime import timezone
from fractions import Fraction
from typing import Any, Callable, Dict, List, Optional, Tuple

import rstr
from faker import Faker

from .helpers import to_type

try:  # Python 3.11+
    from re._constants import MAXREPEAT
except ImportError:  # pragma: no cover
    from sre_constants import MAXREPEAT  # type: ignore[no-redef]

fake = Faker()

# Candidates drawn from Faker or rstr before a string is built to length
# (free-form formats) or the schema is declared unsatisfiable.
STRING_ATTEMPTS = 50

# Rounds of candidates for fixed-shape formats (uuid, ipv4, ...): only the
# formats with several renderings benefit from more than one.
FIXED_SHAPE_ATTEMPTS = 10

# Candidate factors tried for a float ``multipleOf`` before the schema is
# declared unsatisfiable (float rounding can make a factor unusable).
MULTIPLE_ATTEMPTS = 64

# rstr's own cap on open-ended repeats (``+``, ``*``, ``{n,}``).
DEFAULT_REPEAT_LIMIT = 100

# Formats whose values have a fixed shape: a length constraint can only be
# checked, not steered, so an impossible one raises.
FIXED_SHAPE_FORMATS = frozenset(
    {"uuid", "ipv4", "ipv6", "date", "time", "date-time"}
)
# Formats whose values can be built to any reasonable length.
FREE_FORM_FORMATS = frozenset({"email", "uri", "url", "hostname", "phone"})

_LETTERS = string.ascii_lowercase
_ALNUM = string.ascii_lowercase + string.digits


class _BoundedXeger(rstr.Xeger):
    """``rstr.Xeger`` with a configurable cap, and an optional floor, on
    open-ended repeats (``+``, ``*``, ``{n,}``).

    rstr caps those at a module-wide ``STAR_PLUS_LIMIT`` of 100, which
    makes ``maxLength`` hard to meet and ``{200,}`` impossible. The
    override replaces ``_handle_repeat`` entirely; it relies on rstr's
    private ``_handle_state`` and ``_random`` (``tests/test_scalar_constraints.py``
    pins that contract so an rstr upgrade breaking it is caught).
    """

    def __init__(
        self, limit: int, floor: int = 0, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._repeat_limit = max(int(limit), 0)
        self._repeat_floor = max(int(floor), 0)

    def _handle_repeat(
        self, start_range: int, end_range: int, value: Any
    ) -> str:
        if end_range >= MAXREPEAT:  # open-ended: +, *, {n,}
            start_range = max(
                start_range, min(self._repeat_floor, self._repeat_limit)
            )
            end_range = max(start_range, self._repeat_limit)
        times = self._random.randint(start_range, end_range)
        return "".join(
            "".join(self._handle_state(state) for state in value)
            for _ in range(times)
        )


def _random_chars(n: int, alphabet: str = _LETTERS) -> str:
    return "".join(random.choice(alphabet) for _ in range(n))


def _hostname_of_length(n: int) -> str:
    """A syntactically valid hostname of exactly *n* characters
    (1 <= n <= 253): dot-separated labels of at most 63 characters."""
    if not 1 <= n <= 253:
        raise ValueError(f"no hostname has length {n}")
    labels = max(2 if n >= 3 else 1, math.ceil((n + 1) / 64))
    chars = n - (labels - 1)
    base, extra = divmod(chars, labels)
    sizes = [base + (1 if i < extra else 0) for i in range(labels)]
    return ".".join(_random_chars(size) for size in sizes)


def _email_of_length(n: int) -> str:
    """``local@host`` of exactly *n* characters (3 <= n <= 318)."""
    if not 3 <= n <= 318:
        raise ValueError(f"no email address has length {n}")
    host_len = max(1, min(n - 2, 11))
    local_len = n - 1 - host_len
    if local_len > 64:
        local_len = 64
        host_len = n - 1 - local_len
    host = "example.com" if host_len == 11 else _hostname_of_length(host_len)
    return f"{_random_chars(local_len, _ALNUM)}@{host}"


def _uri_of_length(n: int) -> str:
    """An ``http://host/path`` URL of exactly *n* characters (n >= 10)."""
    if n < 10:
        raise ValueError(f"no URL has length {n}")
    if n == 10:
        return f"http://{_hostname_of_length(3)}"
    host_len = min(11, n - 8)
    path_len = n - 7 - host_len - 1
    return f"http://{_hostname_of_length(host_len)}/{_random_chars(path_len)}"


def _phone_of_length(n: int) -> str:
    if n < 1:
        raise ValueError("no phone number has length 0")
    if n == 1:
        return _random_chars(1, string.digits)
    return "+" + _random_chars(n - 1, string.digits)


# (builder, shortest, longest) per free-form format
_FREE_FORM_BUILDERS: Dict[str, Tuple[Callable[[int], str], int, int]] = {
    "email": (_email_of_length, 3, 318),
    "hostname": (_hostname_of_length, 1, 253),
    "uri": (_uri_of_length, 10, 100_000),
    "url": (_uri_of_length, 10, 100_000),
    "phone": (_phone_of_length, 1, 100_000),
}


class DefaultValueGenerator:
    """
    A class to generate default values for various data types.

    Constraints the schema states are honoured; when no value can satisfy
    them (``minLength > maxLength``, an empty numeric range, a ``uuid``
    with ``maxLength: 10``, a pattern that cannot reach ``minLength``...)
    a :class:`ValueError` naming the schema is raised rather than an
    invalid value returned.
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

    @staticmethod
    def _unsatisfiable(what: str, schema: Dict[str, Any]) -> ValueError:
        return ValueError(
            f"Cannot generate {what} for schema "
            f"{json.dumps(schema, default=str)}"
        )

    # ------------------------------------------------------------------
    # strings
    # ------------------------------------------------------------------

    def _string_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate string data honouring format, pattern and length.

        ``minLength``/``maxLength`` apply in every branch:

        * fixed-shape formats (``uuid``, ``ipv4``, ``ipv6``, ``date``,
          ``time``, ``date-time``) are drawn a few times and must fit;
        * free-form formats (``email``, ``uri``, ``url``, ``hostname``,
          ``phone``) are drawn from Faker first and then built to a
          fitting length;
        * a ``pattern`` is drawn with its open-ended repeats capped at
          ``maxLength`` (and floored at ``minLength`` as a second try);
        * unknown formats are annotations and take the plain path.

        Raises ``ValueError`` when the constraints cannot be met.
        """
        min_length, max_length = self._length_bounds(schema)
        fmt = schema.get("format")
        pattern = schema.get("pattern")

        if isinstance(fmt, str) and fmt in FIXED_SHAPE_FORMATS:
            return lambda: self._fixed_shape(
                fmt, min_length, max_length, schema
            )
        if isinstance(fmt, str) and fmt in FREE_FORM_FORMATS:
            return lambda: self._free_form(fmt, min_length, max_length, schema)
        if isinstance(pattern, str):
            return self._pattern_generator(
                pattern, min_length, max_length, schema
            )
        if min_length is None and max_length is None:
            return lambda: fake.word()
        low = min_length if min_length is not None else min(5, max_length)
        high = max_length if max_length is not None else low + 10
        return lambda: fake.pystr(min_chars=low, max_chars=high)

    def _length_bounds(
        self, schema: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Return ``(minLength, maxLength)`` as ints, validated."""
        bounds: List[Optional[int]] = []
        for key in ("minLength", "maxLength"):
            raw = schema.get(key)
            if raw is None or isinstance(raw, bool):
                bounds.append(None)
                continue
            try:
                bounds.append(max(int(raw), 0))
            except (TypeError, ValueError):
                bounds.append(None)
        min_length, max_length = bounds
        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise self._unsatisfiable(
                f"a string: minLength={min_length} exceeds "
                f"maxLength={max_length}",
                schema,
            )
        return min_length, max_length

    @staticmethod
    def _fits(
        value: str, min_length: Optional[int], max_length: Optional[int]
    ) -> bool:
        n = len(value)
        if min_length is not None and n < min_length:
            return False
        return max_length is None or n <= max_length

    def _fixed_shape(
        self,
        fmt: str,
        min_length: Optional[int],
        max_length: Optional[int],
        schema: Dict[str, Any],
    ) -> str:
        candidates = self._format_candidates(fmt)
        if min_length is None and max_length is None:
            return candidates[0]()
        for _ in range(FIXED_SHAPE_ATTEMPTS):
            for make in candidates:
                value = make()
                if self._fits(value, min_length, max_length):
                    return value
        raise self._unsatisfiable(
            f"a '{fmt}' string with minLength={min_length} "
            f"maxLength={max_length}",
            schema,
        )

    def _free_form(
        self,
        fmt: str,
        min_length: Optional[int],
        max_length: Optional[int],
        schema: Dict[str, Any],
    ) -> str:
        make = self._format_candidates(fmt)[0]
        if min_length is None and max_length is None:
            return make()
        for _ in range(STRING_ATTEMPTS):
            value = make()
            if self._fits(value, min_length, max_length):
                return value
        build, shortest, longest = _FREE_FORM_BUILDERS[fmt]
        low = max(min_length or 0, shortest)
        high = min(max_length if max_length is not None else low + 10, longest)
        if low > high:
            raise self._unsatisfiable(
                f"a '{fmt}' string with minLength={min_length} "
                f"maxLength={max_length}",
                schema,
            )
        return build(random.randint(low, high))

    def _pattern_generator(
        self,
        pattern: str,
        min_length: Optional[int],
        max_length: Optional[int],
        schema: Dict[str, Any],
    ) -> Callable:
        limit = (
            max_length
            if max_length is not None
            else max(min_length or 0, DEFAULT_REPEAT_LIMIT)
        )
        capped = _BoundedXeger(limit)
        if min_length is None and max_length is None:
            return lambda: capped.xeger(pattern)
        floored = _BoundedXeger(limit, floor=min_length or 0)

        def draw() -> str:
            for xeger in (capped, floored):
                for _ in range(STRING_ATTEMPTS):
                    value = xeger.xeger(pattern)
                    if self._fits(value, min_length, max_length):
                        return value
            raise self._unsatisfiable(
                f"a string matching {pattern!r} with "
                f"minLength={min_length} maxLength={max_length}",
                schema,
            )

        return draw

    # ------------------------------------------------------------------
    # numbers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _bound(
        self, schema: Dict[str, Any], key: str
    ) -> Tuple[Optional[float], bool]:
        """Return ``(value, exclusive)`` for ``minimum`` or ``maximum``.

        Handles both the draft-4 / OpenAPI 3.0 boolean form of
        ``exclusiveMinimum``/``exclusiveMaximum`` (which qualifies the
        plain bound) and the draft-6+ numeric form. When the plain and
        the numeric exclusive bound are both given, the tighter one wins.
        """
        ex_key = "exclusiveMinimum" if key == "minimum" else "exclusiveMaximum"
        base = self._to_number(schema.get(key))
        raw_exclusive = schema.get(ex_key)
        if isinstance(raw_exclusive, bool):
            return base, bool(raw_exclusive and base is not None)
        exclusive = self._to_number(raw_exclusive)
        if exclusive is None:
            return base, False
        if base is None:
            return exclusive, True
        if key == "minimum":
            return (exclusive, True) if exclusive >= base else (base, False)
        return (exclusive, True) if exclusive <= base else (base, False)

    @staticmethod
    def _multiple_of(schema: Dict[str, Any]) -> Optional[Fraction]:
        value = schema.get("multipleOf")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value <= 0 or not math.isfinite(value):
            return None
        return (
            Fraction(str(value))
            if isinstance(value, float)
            else Fraction(value)
        )

    @staticmethod
    def _fraction(value: float) -> Fraction:
        return (
            Fraction(str(value))
            if isinstance(value, float)
            else Fraction(value)
        )

    def _integer_range(
        self, schema: Dict[str, Any], default_low: int, default_high: int
    ) -> Tuple[int, int, bool, bool]:
        """Inclusive integer bounds and whether each side was derived.

        A missing side is derived from the other by the default span
        (``[bound, bound + 100]`` or ``[bound - 100, bound]``); with no
        bounds at all the default window is used.
        """
        lo, lo_exclusive = self._bound(schema, "minimum")
        hi, hi_exclusive = self._bound(schema, "maximum")
        low = (
            None
            if lo is None
            else (math.floor(lo) + 1 if lo_exclusive else math.ceil(lo))
        )
        high = (
            None
            if hi is None
            else (math.ceil(hi) - 1 if hi_exclusive else math.floor(hi))
        )
        span = default_high - default_low
        low_derived = high_derived = False
        if low is None and high is None:
            low, high = default_low, default_high
            low_derived = high_derived = True
        elif high is None:
            high, high_derived = low + span, True
        elif low is None:
            low, low_derived = high - span, True
        if low > high:
            raise self._unsatisfiable(
                f"an integer: no integer lies within the bounds "
                f"[{low}, {high}]",
                schema,
            )
        return low, high, low_derived, high_derived

    def _integer_generator(
        self,
        schema: Dict[str, Any],
        default_low: int = 0,
        default_high: int = 100,
    ) -> Callable:
        """Generate integer data with range constraints.

        Exclusive bounds are honoured exactly (``floor(x) + 1`` and
        ``ceil(x) - 1``). With ``multipleOf = p/q`` in lowest terms the
        integer multiples are exactly the multiples of ``p``, so a factor
        is drawn directly; a derived (one-sided) bound is widened to reach
        the first multiple.
        """
        low, high, low_derived, high_derived = self._integer_range(
            schema, default_low, default_high
        )
        step = self._multiple_of(schema)
        if step is None:
            return lambda: random.randint(low, high)

        p = step.numerator
        k_low = math.ceil(Fraction(low, p))
        k_high = math.floor(Fraction(high, p))
        if k_low > k_high:
            if high_derived:
                k_high = k_low
            elif low_derived:
                k_low = k_high
            else:
                raise self._unsatisfiable(
                    f"an integer: no multiple of {schema['multipleOf']} "
                    f"lies within [{low}, {high}]",
                    schema,
                )
        return lambda: random.randint(k_low, k_high) * p

    def _number_range(
        self, schema: Dict[str, Any], default_low: float, default_high: float
    ) -> Tuple[float, float, bool, bool, bool, bool]:
        """``(low, high, low_exclusive, high_exclusive, low_derived,
        high_derived)`` for a number schema."""
        lo, lo_exclusive = self._bound(schema, "minimum")
        hi, hi_exclusive = self._bound(schema, "maximum")
        span = float(default_high) - float(default_low)
        low_derived = high_derived = False
        if lo is None and hi is None:
            lo, hi = float(default_low), float(default_high)
            low_derived = high_derived = True
        elif hi is None:
            hi, hi_exclusive, high_derived = lo + span, False, True
        elif lo is None:
            lo, lo_exclusive, low_derived = hi - span, False, True
        if lo > hi or (lo == hi and (lo_exclusive or hi_exclusive)):
            raise self._unsatisfiable(
                f"a number: the bounds leave no value between {lo} and {hi}",
                schema,
            )
        return lo, hi, lo_exclusive, hi_exclusive, low_derived, high_derived

    def _number_generator(self, schema: Dict[str, Any]) -> Callable:
        """Generate number data with range constraints.

        Exclusive bounds are honoured by drawing from the open interval
        (the nearest representable float inside each bound). With
        ``multipleOf``, a factor is drawn and the value is checked the
        way validators do (``value / multipleOf`` must be integral in
        floating point); the candidates are enumerated when few.
        """
        low, high, low_exclusive, high_exclusive, low_derived, high_derived = (
            self._number_range(schema, 0.0, 1.0)
        )
        step = self._multiple_of(schema)
        if step is None:
            open_low = math.nextafter(low, math.inf) if low_exclusive else low
            open_high = (
                math.nextafter(high, -math.inf) if high_exclusive else high
            )
            if open_low > open_high:
                raise self._unsatisfiable(
                    f"a number: the bounds leave no value between "
                    f"{low} and {high}",
                    schema,
                )
            return lambda: random.uniform(open_low, open_high)

        k_low = math.ceil(self._fraction(low) / step)
        if low_exclusive and k_low * step == self._fraction(low):
            k_low += 1
        k_high = math.floor(self._fraction(high) / step)
        if high_exclusive and k_high * step == self._fraction(high):
            k_high -= 1
        if k_low > k_high:
            if high_derived:
                k_high = k_low
            elif low_derived:
                k_low = k_high
            else:
                raise self._unsatisfiable(
                    f"a number: no multiple of {schema['multipleOf']} lies "
                    f"within the bounds {low}..{high}",
                    schema,
                )
        multiple = schema["multipleOf"]
        return lambda: self._float_multiple(
            k_low, k_high, step, multiple, schema
        )

    @staticmethod
    def _is_multiple(value: float, multiple: Any) -> bool:
        """The check validators apply to ``multipleOf``."""
        if isinstance(multiple, float):
            quotient = value / multiple
            return math.isfinite(quotient) and quotient == int(quotient)
        return value % multiple == 0

    def _float_multiple(
        self,
        k_low: int,
        k_high: int,
        step: Fraction,
        multiple: Any,
        schema: Dict[str, Any],
    ) -> float:
        count = k_high - k_low + 1
        factors = (
            random.sample(range(k_low, k_high + 1), count)
            if count <= MULTIPLE_ATTEMPTS
            else [
                random.randint(k_low, k_high) for _ in range(MULTIPLE_ATTEMPTS)
            ]
        )
        for k in factors:
            value = float(k * step)
            if self._is_multiple(value, multiple):
                return value
        raise self._unsatisfiable(
            f"a number: no multiple of {multiple} within the bounds "
            "survives floating point division (validators would reject "
            "every candidate)",
            schema,
        )

    # ------------------------------------------------------------------
    # formats
    # ------------------------------------------------------------------

    @staticmethod
    def _format_candidates(fmt: str) -> List[Callable[[], str]]:
        """Renderings of *fmt*, preferred first. ``date-time`` and
        ``time`` carry a UTC offset so that they are valid RFC 3339."""
        if fmt == "date-time":
            return [
                lambda: fake.date_time_this_decade(
                    tzinfo=timezone.utc
                ).isoformat(),
                lambda: fake.date_time_this_decade(tzinfo=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                lambda: fake.date_time_this_decade(tzinfo=timezone.utc)
                .replace(microsecond=0)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            ]
        if fmt == "time":
            return [
                lambda: f"{fake.time()}Z",
                lambda: f"{fake.time()}+00:00",
                lambda: f"{fake.time(pattern='%H:%M:%S.%f')}Z",
            ]
        simple: Dict[str, Callable[[], str]] = {
            "email": lambda: fake.email(),
            "date": lambda: fake.date_this_decade().isoformat(),
            "phone": lambda: fake.phone_number(),
            "uri": lambda: fake.uri(),
            "url": lambda: fake.url(),
            "hostname": lambda: fake.domain_name(),
            "ipv4": lambda: fake.ipv4(),
            "ipv6": lambda: fake.ipv6(),
            "uuid": lambda: fake.uuid4(),
        }
        return [simple[fmt]]

    def _format_generator(self, fmt: str) -> Callable:
        """Generate data based on format (kept for callers that want a
        bare format value)."""
        if fmt in FIXED_SHAPE_FORMATS or fmt in FREE_FORM_FORMATS:
            return self._format_candidates(fmt)[0]
        return lambda: fake.word()
