"""JSON Schema Sample Builder Library.

This module provides utilities for generating sample data from JSON schemas.
The library supports scenarios for customizing sample generation and a builder
pattern for managing generation state.
"""

from __future__ import annotations

from .break_enum import (
    BreakSite,
    collect_break_sites,
    enumerate_break_scenarios,
    merge_break_scenarios,
    random_break_scenario,
)
from .break_validate import (
    BreakScenarioReport,
    RuleCheck,
    ValidationFailure,
    check_break_scenario,
    validate_breaks,
)
from .breaker import SampleBreaker, apply_break_scenario
from .DefaultValueGenerator import DefaultValueGenerator
from .helpers.utils import duuid
from .JSONSchemaGenerator import JSONSchemaGenerator
from .models.break_models import BreakKind, BreakRule, BreakScenario
from .scenario_enum import (
    VariantSite,
    cartesian_scenarios,
    collect_variant_sites,
    minimal_scenarios,
)
from .SchemaGeneratorBuilder import SchemaGeneratorBuilder

__version__ = "0.4.0"

__all__ = [
    "JSONSchemaGenerator",
    "DefaultValueGenerator",
    "duuid",
    "SchemaGeneratorBuilder",
    "VariantSite",
    "collect_variant_sites",
    "cartesian_scenarios",
    "minimal_scenarios",
    # Break scenarios
    "BreakKind",
    "BreakRule",
    "BreakScenario",
    "BreakSite",
    "collect_break_sites",
    "enumerate_break_scenarios",
    "random_break_scenario",
    "merge_break_scenarios",
    "SampleBreaker",
    "apply_break_scenario",
    "ValidationFailure",
    "validate_breaks",
    "RuleCheck",
    "BreakScenarioReport",
    "check_break_scenario",
]
