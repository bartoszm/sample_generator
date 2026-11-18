"""A recursive ``$ref`` resolved up front: ``Schema.from_oas`` and
``Schema.from_raw_data`` hand it over as a structure that contains itself.
The generator generates from the document the schema was loaded from, with
its ``$ref``s unresolved, the way any schema written with ``$ref`` is
generated (issue #16)."""

from __future__ import annotations

import importlib
import json
import random
import time
import warnings

import pytest
from faker import Faker
from jsonschema import Draft202012Validator

from json_sample_generator import JSONSchemaGenerator
from json_sample_generator.helpers.utils import unresolved_root
from json_sample_generator.models import Scenario, Schema

REF = "#/components/schemas/"


def _oas(**schemas):
    return {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {},
        "components": {"schemas": schemas},
    }


def _oas_validator(oas, name):
    """Validates against the unresolved document, which jsonschema
    resolves lazily."""
    return Draft202012Validator(
        {"$ref": REF + name, "components": oas["components"]},
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def _generate_many(schema, validator=None, n=30):
    gen = JSONSchemaGenerator(schema)
    outputs = []
    for seed in range(n):
        random.seed(seed)
        Faker.seed(seed)
        out = gen.generate()
        if validator is not None:
            errors = [e.message for e in validator.iter_errors(out)]
            assert not errors, (seed, out, errors)
        outputs.append(out)
    return outputs


def _same_samples(a, b, n=30):
    for seed in range(n):
        samples = []
        for schema in (a, b):
            random.seed(seed)
            Faker.seed(seed)
            samples.append(JSONSchemaGenerator(schema).generate())
        assert samples[0] == samples[1], seed


ITEM_OAS = _oas(
    Item={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "item": {"type": "array", "items": {"$ref": REF + "Item"}},
        },
    },
    Quote={
        "type": "object",
        "required": ["item"],
        "properties": {
            "item": {"type": "array", "items": {"$ref": REF + "Item"}}
        },
    },
)

SELF = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "item": {"type": "array", "items": {"$ref": "#"}},
    },
}

# Recursive shapes of tests/test_containers_depth_unique.py and
# tests/test_variant_merge.py.
BRANCHING_REQUIRED = {
    "type": "object",
    "required": ["root"],
    "properties": {"root": {"$ref": "#/$defs/T"}},
    "$defs": {
        "T": {
            "type": "object",
            "required": ["c0", "c1"],
            "properties": {
                "c0": {"$ref": "#/$defs/T"},
                "c1": {"$ref": "#/$defs/T"},
            },
        }
    },
}

RECURSIVE_ONEOF = {
    "type": "object",
    "required": ["root"],
    "properties": {"root": {"$ref": "#/$defs/T"}},
    "$defs": {
        "T": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["v"],
                    "properties": {"v": {"type": "integer"}},
                },
                {
                    "type": "object",
                    "required": ["c0", "c1", "c2"],
                    "properties": {
                        "c0": {"$ref": "#/$defs/T"},
                        "c1": {"$ref": "#/$defs/T"},
                        "c2": {"$ref": "#/$defs/T"},
                    },
                },
            ]
        }
    },
}

RECURSIVE_ONEOF_ALLOF = {
    "type": "object",
    "required": ["root"],
    "properties": {"root": {"$ref": "#/$defs/T"}},
    "$defs": {
        "T": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["v"],
                    "properties": {"v": {"type": "integer"}},
                },
                {
                    "allOf": [
                        {
                            "type": "object",
                            "required": ["a"],
                            "properties": {"a": {"type": "string"}},
                        },
                        {
                            "required": ["c"],
                            "properties": {"c": {"$ref": "#/$defs/T"}},
                        },
                    ]
                },
            ]
        }
    },
}

REFINED_NODE = {
    "definitions": {
        "Base": {
            "type": "object",
            "required": ["v"],
            "properties": {
                "v": {"type": "string"},
                "next": {"$ref": "#/definitions/Node"},
            },
        },
        "Node": {
            "allOf": [
                {"$ref": "#/definitions/Base"},
                {
                    "properties": {
                        "next": {"$ref": "#/definitions/Node"},
                        "kind": {"oneOf": [{"const": "x"}, {"const": "y"}]},
                    }
                },
            ]
        },
    },
    "type": "object",
    "required": ["root"],
    "properties": {"root": {"$ref": "#/definitions/Node"}},
}


# ---------------------------------------------------------------------------
# The reports of issue #16
# ---------------------------------------------------------------------------


def test_from_oas_component_holding_a_list_of_itself_generates():
    schema = Schema.from_oas(ITEM_OAS, name="Quote")
    outputs = _generate_many(schema, _oas_validator(ITEM_OAS, "Quote"))
    # the recursion is really generated: an Item holding Items
    assert any(
        item.get("item") for out in outputs for item in out["item"]
    ), outputs


def test_from_raw_data_self_reference_generates():
    schema = Schema.from_raw_data(SELF, base_uri="file:///item.json")
    outputs = _generate_many(schema, Draft202012Validator(SELF))
    assert any(out.get("item") for out in outputs)


# ---------------------------------------------------------------------------
# Generated the way the same schema written with $ref is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        SELF,
        {
            "type": "object",
            "required": ["child"],
            "properties": {"child": {"$ref": "#"}},
        },
        REFINED_NODE,
        RECURSIVE_ONEOF,
        RECURSIVE_ONEOF_ALLOF,
        BRANCHING_REQUIRED,
    ],
    ids=[
        "self",
        "required-self",
        "refined-node",
        "recursive-oneof",
        "recursive-oneof-allof",
        "branching-required",
    ],
)
def test_from_raw_data_generates_what_the_unresolved_schema_does(raw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _same_samples(
            Schema(data=raw, base_uri="file://rec.json"),
            Schema.from_raw_data(raw, "file://rec.json"),
        )


def _unresolved(oas, name):
    """The component *name* as the root of its document, refs unresolved."""
    return Schema(
        data={
            **oas["components"]["schemas"][name],
            "components": oas["components"],
        },
        base_uri="file:///oas.json",
    )


def _same_without_components(a, b, n=30):
    for seed in range(n):
        samples = []
        for schema in (a, b):
            random.seed(seed)
            Faker.seed(seed)
            out = JSONSchemaGenerator(schema).generate()
            out.pop("components", None)
            samples.append(out)
        assert samples[0] == samples[1], seed


R = "#/components/schemas/"
BASE = {"type": "object", "properties": {"id": {"type": "string"}}}

# OpenAPI inheritance: each type is an allOf of a shared Base, every one of
# them used once, and a Root that holds a list of itself.
INHERITANCE_OAS = _oas(
    Base=BASE,
    A={
        "allOf": [
            {"$ref": R + "Base"},
            {
                "type": "object",
                "required": ["b"],
                "properties": {"b": {"$ref": R + "B"}},
            },
        ]
    },
    B={
        "allOf": [
            {"$ref": R + "Base"},
            {
                "type": "object",
                "required": ["c"],
                "properties": {"c": {"$ref": R + "C"}},
            },
        ]
    },
    C={
        "allOf": [
            {"$ref": R + "Base"},
            {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "opt": {"type": "string"},
                },
            },
        ]
    },
    Root={
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"$ref": R + "A"},
            "children": {"type": "array", "items": {"$ref": R + "Root"}},
        },
    },
)

# Optional mutual recursion through a component used once.
MUTUAL_OAS = _oas(
    A={
        "type": "object",
        "properties": {"v": {"type": "integer"}, "b": {"$ref": R + "B"}},
    },
    B={
        "type": "object",
        "properties": {"w": {"type": "string"}, "a": {"$ref": R + "A"}},
    },
)


@pytest.mark.parametrize(
    "oas, name",
    [
        (ITEM_OAS, "Quote"),
        (ITEM_OAS, "Item"),
        (INHERITANCE_OAS, "Root"),
        (MUTUAL_OAS, "A"),
    ],
    ids=["no-cycle-at-root", "recursive-root", "inheritance", "mutual"],
)
def test_from_oas_generates_what_the_unresolved_document_does(oas, name):
    # The component as the root of the unresolved document: from_oas
    # records its components, so the generator writes them back as such.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _same_without_components(
            _unresolved(oas, name), Schema.from_oas(oas, name=name)
        )


def test_inheritance_is_not_taken_for_recursion():
    # A, B and C share Base: once inlined, their allOf would make Base look
    # like a node that recurs, and cut c. Generated in full, and valid.
    schema = Schema.from_oas(INHERITANCE_OAS, name="Root")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        outputs = _generate_many(
            schema, _oas_validator(INHERITANCE_OAS, "Root")
        )
    assert all("opt" in out["a"]["b"]["c"] for out in outputs)


def test_from_raw_data_with_a_fragment_generates_what_the_document_does(
    tmp_path,
):
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(INHERITANCE_OAS))
    resolved = Schema.from_raw_data(
        INHERITANCE_OAS, f"{path.as_uri()}#/components/schemas/Root"
    )
    _same_without_components(_unresolved(INHERITANCE_OAS, "Root"), resolved)


def test_schema_path_names_the_reference_the_document_has():
    def schema_paths(schema):
        seen = set()

        def record(ctx):
            seen.add(ctx.schema_path)
            return "n"

        scenario = Scenario(
            name="s", pattern_overrides=[("item[0].id", record)]
        )
        for seed in range(10):
            random.seed(seed)
            JSONSchemaGenerator(schema).generate(scenario)
        return seen

    resolved = schema_paths(Schema.from_oas(ITEM_OAS, name="Item"))
    assert resolved == schema_paths(_unresolved(ITEM_OAS, "Item"))
    assert resolved == {R + "Item"}


# ---------------------------------------------------------------------------
# The cycle rule ends recursion through allOf, the OpenAPI inheritance shape
# ---------------------------------------------------------------------------

BASE = {"type": "object", "properties": {"id": {"type": "string"}}}


def _node_oas(**node_props):
    required = [k for k in node_props if not k.startswith("opt")]
    return _oas(
        Base=BASE,
        Node={
            "allOf": [
                {"$ref": REF + "Base"},
                {
                    "type": "object",
                    "required": required,
                    "properties": node_props,
                },
            ]
        },
    )


def test_required_recursion_through_allof_is_cut_and_warns():
    oas = _node_oas(child={"$ref": REF + "Node"})
    gen = JSONSchemaGenerator(Schema.from_oas(oas, name="Node"))
    random.seed(0)
    with pytest.warns(UserWarning, match="recursion limit"):
        out = gen.generate()
    # child: first occurrence of Node (full); child.child: second (required
    # members only); child.child.child: third, cut
    assert set(out["child"]) == {"id", "child"}
    assert out["child"]["child"] == {}


def test_branching_required_recursion_through_allof_warns_quickly():
    oas = _node_oas(a={"$ref": REF + "Node"}, b={"$ref": REF + "Node"})
    gen = JSONSchemaGenerator(Schema.from_oas(oas, name="Node"))
    started = time.perf_counter()
    with pytest.warns(UserWarning, match="recursion limit"):
        out = gen.generate()
    assert time.perf_counter() - started < 1
    assert {"a", "b"} <= set(out)


def test_optional_recursion_through_allof_terminates_silently():
    oas = _node_oas(optA={"$ref": REF + "Node"}, optB={"$ref": REF + "Node"})
    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _generate_many(
            Schema.from_oas(oas, name="Node"), _oas_validator(oas, "Node")
        )
    assert time.perf_counter() - started < 2


def test_recursive_property_defined_twice_stays_one_reference():
    # Base and Node both define `next`, Node through an inline allOf: the
    # merge wraps the two definitions in a fresh allOf, which the cycle
    # rule sees through only by the reference both of them hold.
    oas = _oas(
        Base={
            "type": "object",
            "required": ["v"],
            "properties": {
                "v": {"type": "string"},
                "next": {"$ref": REF + "Node"},
                "other": {"$ref": REF + "Node"},
            },
        },
        Node={
            "allOf": [
                {"$ref": REF + "Base"},
                {
                    "properties": {
                        "next": {
                            "allOf": [{"$ref": REF + "Node"}],
                            "description": "refined",
                        },
                        "other": {
                            "allOf": [{"$ref": REF + "Node"}],
                            "description": "refined",
                        },
                    }
                },
            ]
        },
    )
    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _generate_many(
            Schema.from_oas(oas, name="Node"), _oas_validator(oas, "Node")
        )
    assert time.perf_counter() - started < 2


def test_polymorphic_item_holding_items_validates():
    # The shape of TMF's QuoteItem in a strict OpenAPI variant: a
    # discriminated allOf whose items hold a list of the same type.
    oas = _oas(
        Entity={
            "type": "object",
            "properties": {
                "@type": {"type": "string"},
                "href": {"type": "string", "format": "uri"},
            },
        },
        QuoteItem={
            "discriminator": {
                "propertyName": "@type",
                "mapping": {"QuoteItem": REF + "QuoteItem"},
            },
            "allOf": [
                {"$ref": REF + "Entity"},
                {
                    "type": "object",
                    "required": ["id", "action"],
                    "properties": {
                        "id": {"type": "string"},
                        "action": {"enum": ["add", "modify", "delete"]},
                        "quoteItem": {
                            "type": "array",
                            "items": {"$ref": REF + "QuoteItem"},
                        },
                    },
                },
            ],
        },
        Quote={
            "type": "object",
            "required": ["quoteItem"],
            "properties": {
                "quoteItem": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": REF + "QuoteItem"},
                }
            },
        },
    )
    outputs = _generate_many(
        Schema.from_oas(oas, name="Quote"), _oas_validator(oas, "Quote")
    )
    assert any(
        item.get("quoteItem") for out in outputs for item in out["quoteItem"]
    )


# ---------------------------------------------------------------------------
# Only a schema that contains itself generates from the source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make",
    [
        lambda: Schema.from_oas(_oas(Base=BASE), name="Base"),
        lambda: Schema.from_raw_data(
            {
                "definitions": {"Base": BASE},
                "type": "object",
                "properties": {"b": {"$ref": "#/definitions/Base"}},
            },
            "file://b.json",
        ),
        lambda: Schema(data=SELF, base_uri="file://rec.json"),
    ],
    ids=["from-oas", "from-raw-data", "unresolved-recursive"],
)
def test_other_schemas_are_not_generated_from_the_source(make, monkeypatch):
    # the package's JSONSchemaGenerator attribute is the class
    cls = importlib.import_module(
        "json_sample_generator.JSONSchemaGenerator"
    ).JSONSchemaGenerator
    calls = []
    monkeypatch.setattr(
        cls,
        "_load_source",
        staticmethod(lambda *args: calls.append(args)),
    )
    JSONSchemaGenerator(make()).generate()
    assert calls == []


def test_a_schema_that_contains_itself_without_a_source_is_refused():
    node = {"type": "object", "properties": {}}
    node["properties"]["child"] = node
    with pytest.raises(ValueError, match="from_oas"):
        JSONSchemaGenerator(Schema(data=node))


def test_the_source_survives_a_copy_of_the_schema():
    schema = Schema.from_oas(ITEM_OAS, name="Item").model_copy()
    assert JSONSchemaGenerator(schema).generate()


def _depths(sample, key):
    depth = 0
    while isinstance(sample.get(key), dict):
        sample = sample[key]
        depth += 1
    return depth


def test_a_fragment_that_shares_a_key_with_its_container_generates(tmp_path):
    # the schema has a "definitions" key of its own, so it cannot be the
    # root in place beside the document's "definitions"
    raw = {
        "definitions": {
            "Node": {
                "type": "object",
                "definitions": {"Leaf": {"type": "string"}},
                "properties": {
                    "leaf": {"$ref": "#/definitions/Node/definitions/Leaf"},
                    "child": {"$ref": "#/definitions/Node"},
                },
            }
        }
    }
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(raw))
    schema = Schema.from_raw_data(raw, f"{path.as_uri()}#/definitions/Node")
    outs = []
    for seed in range(20):
        random.seed(seed)
        outs.append(JSONSchemaGenerator(schema).generate())
    assert all(isinstance(out["leaf"], str) for out in outs)
    # the recursion generates, and ends
    assert any("child" in out for out in outs)
    assert all(_depths(out, "child") <= 3 for out in outs)


def test_a_ref_into_a_top_level_key_other_than_components_resolves():
    oas = _oas(
        Node={
            "type": "object",
            "required": ["p"],
            "properties": {
                "p": {
                    "$ref": "#/paths/~1x/get/responses/200/content/"
                    "application~1json/schema"
                },
                "kids": {"type": "array", "items": {"$ref": REF + "Node"}},
            },
        }
    )
    oas["paths"] = {
        "/x": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"type": "string"}}
                        }
                    }
                }
            }
        }
    }
    out = JSONSchemaGenerator(Schema.from_oas(oas, name="Node")).generate()
    assert isinstance(out["p"], str)


def _write(tmp_path, raw):
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(raw))
    return path.as_uri()


def test_a_hash_reference_under_a_fragment_is_the_document(tmp_path):
    raw = {
        "definitions": {
            "A": {
                "type": "object",
                "required": ["v", "kid"],
                "properties": {
                    "v": {"type": "integer"},
                    "kid": {"$ref": "#"},
                },
            }
        },
        "properties": {"p": {"type": "integer"}},
    }
    schema = Schema.from_raw_data(
        raw, _write(tmp_path, raw) + "#/definitions/A"
    )
    out = JSONSchemaGenerator(schema).generate()
    # "#" is the document, which holds "p", not the schema "A"
    assert set(out["kid"]) == {"p"}


def test_a_fragment_at_a_keyword_does_not_take_in_the_documents_keyword(
    tmp_path,
):
    raw = {
        "type": "object",
        "properties": {
            "a": {
                "type": "object",
                "required": ["n"],
                "properties": {
                    "n": {"type": "integer"},
                    "k": {"$ref": "#/properties/a"},
                },
            },
            "b": {"type": "string"},
        },
    }
    schema = Schema.from_raw_data(
        raw, _write(tmp_path, raw) + "#/properties/a"
    )
    for seed in range(10):
        random.seed(seed)
        out = JSONSchemaGenerator(schema).generate()
        assert "b" not in out and "a" not in out


def test_a_fragment_through_a_ref_generates(tmp_path):
    raw = {
        "definitions": {
            "A": {
                "type": "object",
                "required": ["n"],
                "properties": {
                    "n": {"type": "integer"},
                    "kid": {"$ref": "#/definitions/A"},
                },
            },
            "W": {
                "type": "object",
                "properties": {"a": {"$ref": "#/definitions/A"}},
            },
        }
    }
    schema = Schema.from_raw_data(
        raw,
        _write(tmp_path, raw) + "#/definitions/W/properties/a/properties/kid",
    )
    assert "n" in JSONSchemaGenerator(schema).generate()


def test_the_schema_of_a_generator_generates_again():
    generator = JSONSchemaGenerator(Schema.from_oas(ITEM_OAS, name="Item"))
    again = JSONSchemaGenerator(generator.schema)
    assert again.generate() is not None


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


def test_unresolved_root_is_the_document_without_a_pointer():
    doc = {"type": "object", "properties": {"a": {"$ref": "#"}}}
    assert unresolved_root(doc, ()) == doc


def test_unresolved_root_carries_every_top_level_key():
    doc = {
        "openapi": "3.1.0",
        "paths": {"/x": {}},
        "components": {"schemas": {"A": {"type": "object"}}},
    }
    root = unresolved_root(doc, ("components", "schemas", "A"))
    assert root == {"type": "object", **doc}


@pytest.mark.parametrize(
    "doc, pointer",
    [
        # the schema has a key of the document's top level
        ({"definitions": {"A": {"definitions": {}}}}, ("definitions", "A")),
        # the document is a schema itself
        ({"type": "object", "definitions": {"A": {}}}, ("definitions", "A")),
        # "#" is the document, not the schema
        (
            {"definitions": {"A": {"properties": {"k": {"$ref": "#"}}}}},
            ("definitions", "A"),
        ),
        # the pointer passes a $ref
        (
            {"definitions": {"W": {"$ref": "#/definitions/A"}, "A": {}}},
            ("definitions", "W", "properties"),
        ),
        # the pointer leads nowhere
        ({"definitions": {}}, ("definitions", "A")),
    ],
    ids=["same-key", "schema-document", "hash-ref", "through-ref", "missing"],
)
def test_unresolved_root_gives_up_when_it_cannot_be_the_root(doc, pointer):
    assert unresolved_root(doc, pointer) is None
