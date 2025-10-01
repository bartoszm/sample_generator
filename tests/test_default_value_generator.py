import os
import sys

# ensure local source is imported instead of an installed package
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)


from json_sample_generator.DefaultValueGenerator import DefaultValueGenerator


def sample_many(gen_callable, n=200):
    return [gen_callable() for _ in range(n)]


def test_integer_defaults():
    g = DefaultValueGenerator()({"type": "integer"})
    samples = sample_many(g)
    # default behavior should produce integers; exact default range may vary
    assert all(isinstance(x, int) for x in samples)
    assert len(set(samples)) > 1


def test_integer_with_min_max():
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": 10, "maximum": 20}
    )
    samples = sample_many(g)
    assert all(isinstance(x, int) for x in samples)
    assert all(10 <= x <= 20 for x in samples)


def test_integer_only_min():
    g = DefaultValueGenerator()({"type": "integer", "minimum": 50})
    samples = sample_many(g)
    assert all(isinstance(x, int) for x in samples)
    assert all(50 <= x <= 100 for x in samples)


def test_integer_only_max():
    g = DefaultValueGenerator()({"type": "integer", "maximum": 5})
    samples = sample_many(g)
    assert all(isinstance(x, int) for x in samples)
    # ensure generator respects maximum when provided
    assert all(x <= 5 for x in samples)


def test_integer_exclusive_bounds():
    # exclusiveMinimum should bump min by 1, exclusiveMaximum should reduce max by 1
    schema = {
        "type": "integer",
        "exclusiveMinimum": 10,
        "exclusiveMaximum": 15,
    }
    g = DefaultValueGenerator()(schema)
    samples = sample_many(g)
    assert all(isinstance(x, int) for x in samples)
    assert all(x > 10 and x < 15 for x in samples)


def test_number_defaults():
    g = DefaultValueGenerator()({"type": "number"})
    samples = sample_many(g)
    assert all(isinstance(x, (int, float)) for x in samples)
    # default numeric range may vary; ensure they're numeric and varied
    assert len(set(samples)) > 1


def test_number_with_bounds():
    g = DefaultValueGenerator()(
        {"type": "number", "minimum": 0.5, "maximum": 2.5}
    )
    samples = sample_many(g)
    assert all(0.5 <= x <= 2.5 for x in samples)


def test_number_exclusive_bounds():
    schema = {
        "type": "number",
        "exclusiveMinimum": 0.5,
        "exclusiveMaximum": 2.5,
    }
    g = DefaultValueGenerator()(schema)
    samples = sample_many(g)
    # exclusive adjustments in DefaultValueGenerator use a small shift (0.01)
    assert all(x > 0.5 and x < 2.5 for x in samples)


def test_integer_non_numeric_bounds_fallback():
    # non-numeric min/max should be ignored and defaults used
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": "a", "maximum": "b"}
    )
    samples = sample_many(g)
    assert all(isinstance(x, int) for x in samples)
    assert len(set(samples)) > 1


def test_integer_min_greater_than_max_swapped():
    # min > max should be swapped internally
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": 100, "maximum": 10}
    )
    samples = sample_many(g)
    assert all(10 <= x <= 100 for x in samples)


def test_integer_float_bounds_coercion():
    # float bounds should coerce: ceil(min), floor(max)
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": 1.2, "maximum": 3.8}
    )
    samples = sample_many(g)
    assert all(x in (2, 3) for x in samples)


def test_integer_exclusive_with_non_integer_bounds():
    # exclusive bounds that are floats should be shifted and coerced
    schema = {
        "type": "integer",
        "exclusiveMinimum": 1.2,
        "exclusiveMaximum": 4.8,
    }
    g = DefaultValueGenerator()(schema)
    samples = sample_many(g)
    # exclusiveMinimum -> 1.2 + 1 -> 2.2 -> ceil -> 3
    # exclusiveMaximum -> 4.8 - 1 -> 3.8 -> floor -> 3
    assert all(x == 3 for x in samples)


def test_integer_min_equals_max():
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": 7, "maximum": 7}
    )
    samples = sample_many(g)
    assert all(x == 7 for x in samples)


def test_integer_large_range():
    g = DefaultValueGenerator()(
        {"type": "integer", "minimum": -1000000, "maximum": 1000000}
    )
    samples = sample_many(g, n=50)
    assert all(-1000000 <= x <= 1000000 for x in samples)


def test_number_non_numeric_bounds_fallback():
    g = DefaultValueGenerator()(
        {"type": "number", "minimum": "min", "maximum": None}
    )
    samples = sample_many(g)
    assert all(isinstance(x, (int, float)) for x in samples)
    assert len(set(samples)) > 1
