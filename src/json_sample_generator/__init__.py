from __future__ import annotations

from .DefaultValueGenerator import DefaultValueGenerator
from .helpers.utils import duuid
from .JSONSchemaGenerator import JSONSchemaGenerator
from .SchemaGeneratorBuilder import SchemaGeneratorBuilder

"""
JSON Schema Sample Builder Library

This module provides utilities for generating sample data from JSON schemas.
The library supports scenarios for customizing sample generation and a builder
pattern for managing generation state.
"""

__version__ = "0.1.0"

__all__ = [
    "JSONSchemaGenerator",
    "DefaultValueGenerator",
    "duuid",
    "SchemaGeneratorBuilder",
]
