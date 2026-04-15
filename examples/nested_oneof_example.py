"""Example: Advanced nested oneOf with payment processing schema.

This demonstrates:
- 4-level nested oneOf: payment -> card type -> network -> fraud level
- OpenAPI discriminators for type selection
- Arrays with nested oneOf (transactions with different fee structures)
- Regex-based selectors for array items
- Callable selectors with conditional logic
- Custom overrides combined with variant selection
- Cartesian vs minimal strategies with realistic data
- Title-based and discriminator-based selection
"""

from json_sample_generator import (
    JSONSchemaGenerator,
    cartesian_scenarios,
    collect_variant_sites,
    minimal_scenarios,
)
from json_sample_generator.models import Context, Scenario, Schema

# Schema with 4 levels of nested oneOf + arrays with nested oneOf
schema_data = {
    "type": "object",
    "properties": {
        "payment_id": {"type": "string"},
        "amount": {"type": "number", "minimum": 0},
        "currency": {"type": "string", "enum": ["USD", "EUR", "GBP"]},
        "method": {
            "discriminator": {
                "propertyName": "type",
                "mapping": {
                    "card": "#/components/schemas/CardPayment",
                    "bank": "#/components/schemas/BankTransfer",
                    "wallet": "#/components/schemas/WalletPayment",
                },
            },
            "oneOf": [
                {"$ref": "#/components/schemas/CardPayment"},
                {"$ref": "#/components/schemas/BankTransfer"},
                {"$ref": "#/components/schemas/WalletPayment"},
            ],
        },
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "fee_structure": {
                        "oneOf": [
                            {
                                "title": "Percentage",
                                "type": "object",
                                "properties": {
                                    "rate": {"type": "number"},
                                    "min_fee": {"type": "number"},
                                },
                            },
                            {
                                "title": "Flat",
                                "type": "object",
                                "properties": {"amount": {"type": "number"}},
                            },
                            {
                                "title": "Tiered",
                                "type": "object",
                                "properties": {
                                    "tiers": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "threshold": {
                                                    "type": "number"
                                                },
                                                "rate": {"type": "number"},
                                            },
                                        },
                                    }
                                },
                            },
                        ]
                    },
                },
            },
        },
    },
    "components": {
        "schemas": {
            "CardPayment": {
                "title": "Card",
                "type": "object",
                "properties": {
                    "type": {"const": "card"},
                    "last_four": {"type": "string", "pattern": "^[0-9]{4}$"},
                    "card_brand": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/Visa"},
                            {"$ref": "#/components/schemas/Mastercard"},
                            {"$ref": "#/components/schemas/Amex"},
                        ]
                    },
                },
            },
            "Visa": {
                "title": "Visa",
                "type": "object",
                "properties": {
                    "brand": {"const": "visa"},
                    "bin": {"type": "string"},
                    "network": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/DomesticVisa"},
                            {"$ref": "#/components/schemas/InternationalVisa"},
                        ]
                    },
                },
            },
            "Mastercard": {
                "title": "Mastercard",
                "type": "object",
                "properties": {
                    "brand": {"const": "mastercard"},
                    "bin": {"type": "string"},
                    "network": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/DomesticMC"},
                            {"$ref": "#/components/schemas/InternationalMC"},
                        ]
                    },
                },
            },
            "Amex": {
                "title": "Amex",
                "type": "object",
                "properties": {
                    "brand": {"const": "amex"},
                    "member_since": {"type": "string", "format": "date"},
                    "network": {
                        "oneOf": [
                            {
                                "title": "Standard",
                                "type": "object",
                                "properties": {"tier": {"const": "standard"}},
                            },
                            {
                                "title": "Premium",
                                "type": "object",
                                "properties": {
                                    "tier": {"const": "premium"},
                                    "concierge": {"type": "boolean"},
                                },
                            },
                        ]
                    },
                },
            },
            "DomesticVisa": {
                "title": "Domestic",
                "type": "object",
                "properties": {
                    "region": {"const": "domestic"},
                    "fraud_check": {
                        "oneOf": [
                            {
                                "title": "Basic",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "basic"},
                                    "cvv_required": {"type": "boolean"},
                                },
                            },
                            {
                                "title": "Advanced",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "advanced"},
                                    "cvv_required": {"type": "boolean"},
                                    "3ds_enabled": {"type": "boolean"},
                                    "risk_score": {"type": "number"},
                                },
                            },
                        ]
                    },
                },
            },
            "InternationalVisa": {
                "title": "International",
                "type": "object",
                "properties": {
                    "region": {"const": "international"},
                    "country_code": {"type": "string"},
                    "fraud_check": {
                        "oneOf": [
                            {
                                "title": "Basic",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "basic"},
                                    "cvv_required": {"type": "boolean"},
                                },
                            },
                            {
                                "title": "Enhanced",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "enhanced"},
                                    "cvv_required": {"type": "boolean"},
                                    "3ds_enabled": {"type": "boolean"},
                                    "risk_score": {"type": "number"},
                                    "sanctions_check": {"type": "boolean"},
                                },
                            },
                        ]
                    },
                },
            },
            "DomesticMC": {
                "title": "Domestic",
                "type": "object",
                "properties": {
                    "region": {"const": "domestic"},
                    "fraud_check": {
                        "oneOf": [
                            {
                                "title": "Basic",
                                "type": "object",
                                "properties": {"level": {"const": "basic"}},
                            },
                            {
                                "title": "Advanced",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "advanced"},
                                    "securecode": {"type": "boolean"},
                                },
                            },
                        ]
                    },
                },
            },
            "InternationalMC": {
                "title": "International",
                "type": "object",
                "properties": {
                    "region": {"const": "international"},
                    "country_code": {"type": "string"},
                    "fraud_check": {
                        "oneOf": [
                            {
                                "title": "Basic",
                                "type": "object",
                                "properties": {"level": {"const": "basic"}},
                            },
                            {
                                "title": "Enhanced",
                                "type": "object",
                                "properties": {
                                    "level": {"const": "enhanced"},
                                    "securecode": {"type": "boolean"},
                                    "idcheck": {"type": "boolean"},
                                },
                            },
                        ]
                    },
                },
            },
            "BankTransfer": {
                "title": "Bank",
                "type": "object",
                "properties": {
                    "type": {"const": "bank"},
                    "routing_number": {"type": "string"},
                    "account_type": {"enum": ["checking", "savings"]},
                },
            },
            "WalletPayment": {
                "title": "Wallet",
                "type": "object",
                "properties": {
                    "type": {"const": "wallet"},
                    "provider": {
                        "enum": ["paypal", "apple_pay", "google_pay"]
                    },
                    "account_id": {"type": "string"},
                },
            },
        }
    },
}

schema = Schema.from_raw_data(schema_data, base_uri="file://payment.json")


def print_separator(title: str):
    """Print a formatted section separator."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def print_scenario_info(scenario, index: int):
    """Print scenario metadata."""
    print(f"[{index}] {scenario.name}")
    print(f"    Description: {scenario.description}")
    print(f"    Selectors: {scenario.oneof_selectors}")


def print_sample(sample: dict, indent: int = 4):
    """Print generated sample in a readable format."""
    import json

    print(json.dumps(sample, indent=indent))


# Discover all variant sites
print_separator("STEP 1: Discover All Variant Sites")

sites = collect_variant_sites(schema)
print(f"Found {len(sites)} variant sites:\n")
for i, site in enumerate(sites, 1):
    print(f"{i}. Path: '{site.path}'")
    print(f"   Kind: {site.kind}")
    print(f"   Count: {site.count} variants")
    print(f"   Names: {', '.join(site.names)}")
    print()

print("Note: Sites at different depths show the nested structure:")
print("  - Level 1: method (Card, Bank, Wallet)")
print("  - Level 2: card_brand (Visa, Mastercard, Amex)")
print("  - Level 3: network (Domestic, International, or Amex tiers)")
print("  - Level 4: fraud_check (Basic, Advanced, Enhanced)")
print("  - Array: transactions[*].fee_structure (Percentage, Flat, Tiered)")
print()

# Strategy 1: Cartesian product (all combinations)
print_separator("STEP 2: Cartesian Strategy - First 5 Scenarios")

try:
    cartesian = cartesian_scenarios(schema)
    print(f"Generated {len(cartesian)} scenarios\n")
except ValueError as e:
    print(f"Cartesian too large, using limit: {e}\n")
    cartesian = cartesian_scenarios(schema, max_scenarios=100)
    print(f"Generated {len(cartesian)} scenarios\n")

gen = JSONSchemaGenerator(schema=schema)

# Show first 5 instead of all to keep output manageable
for idx, scenario in enumerate(cartesian[:5]):
    print_scenario_info(scenario, idx)
    sample = gen.generate(scenario)
    print_sample(sample)
    print()

print(f"... and {len(cartesian) - 5} more scenarios")
print()

# Strategy 2: Minimal coverage (every variant appears at least once)
print_separator("STEP 3: Minimal Strategy - Efficient Coverage")

minimal_raw = minimal_scenarios(schema)
print(f"Generated {len(minimal_raw)} scenarios (minimal 1-wise coverage)\n")

# Generate samples (this will normalize scenarios internally)
minimal_samples = []
for idx, scenario in enumerate(minimal_raw):
    print_scenario_info(scenario, idx)
    sample = gen.generate(scenario)
    minimal_samples.append(sample)
    print_sample(sample)
    print()

# Comparison
print_separator("STEP 4: Strategy Comparison")

print(f"Variant sites discovered: {len(sites)}")
print(f"Site counts: {[s.count for s in sites]}")
print()
print(f"Cartesian scenarios: {len(cartesian)}")
print("  Formula: product of all reachable combinations")
print(
    "  Note: Nested sites are only reachable through specific parent choices"
)
print()
print(f"Minimal scenarios: {len(minimal_raw)}")
print(
    f"  Formula: max({[s.count for s in sites]}) = {max(s.count for s in sites)}"
)
print("  Every variant of every site appears in at least one scenario")
print()

# Show which variants appear in minimal set (first few paths)
minimal_for_display = minimal_scenarios(schema)
print("Coverage matrix for minimal strategy (showing main paths):")
print("-" * 100)
print(
    f"{'Scenario':<12} {'method':<8} {'card_brand':<12} {'network':<15} {'fraud':<10}"
)
print("-" * 100)

for scenario in minimal_for_display[:5]:  # Show first 5
    selectors = scenario.oneof_selectors

    # Extract indices by calling the normalized lambdas
    method_idx = selectors.get("method", lambda c, s: 0)(None, None)

    # Find the appropriate site for each level
    method_site = next((s for s in sites if s.path == "method"), None)
    brand_site = next(
        (s for s in sites if s.path == "method.card_brand"), None
    )

    method = (
        method_site.names[method_idx]
        if method_site and method_idx < len(method_site.names)
        else f"idx{method_idx}"
    )

    # Only show card details if Card is selected
    if method == "Card":
        brand_key = "method.card_brand"
        brand_idx = selectors.get(brand_key, lambda c, s: 0)(None, None)
        brand = (
            brand_site.names[brand_idx]
            if brand_site and brand_idx < len(brand_site.names)
            else f"idx{brand_idx}"
        )

        # Network and fraud check paths vary by brand
        network_path = "method.card_brand.network"
        network_site = next((s for s in sites if s.path == network_path), None)
        if network_site:
            network_idx = selectors.get(network_path, lambda c, s: 0)(
                None, None
            )
            network = (
                network_site.names[network_idx]
                if network_idx < len(network_site.names)
                else f"idx{network_idx}"
            )
        else:
            network = "N/A"

        fraud_path = "method.card_brand.network.fraud_check"
        fraud_site = next((s for s in sites if s.path == fraud_path), None)
        if fraud_site:
            fraud_idx = selectors.get(fraud_path, lambda c, s: 0)(None, None)
            fraud = (
                fraud_site.names[fraud_idx]
                if fraud_idx < len(fraud_site.names)
                else f"idx{fraud_idx}"
            )
        else:
            fraud = "N/A"
    else:
        brand = "N/A"
        network = "N/A"
        fraud = "N/A"

    print(
        f"{scenario.name:<12} {method:<8} {brand:<12} {network:<15} {fraud:<10}"
    )

if len(minimal_for_display) > 5:
    print(f"... and {len(minimal_for_display) - 5} more scenarios")

print("-" * 100)

# Demonstrate advanced manual selection patterns
print_separator("STEP 5: Advanced Manual Selection Patterns")


# Helper function used across multiple patterns
def generate_card_last_four(ctx: Context) -> str:
    """Generate last 4 digits based on card brand."""
    brand = (
        ctx.data.get("method", {})
        .get("card_brand", {})
        .get("brand", "unknown")
    )
    # Visa starts with 4, MC with 5, Amex with 37
    if brand == "visa":
        return "4123"
    elif brand == "mastercard":
        return "5678"
    elif brand == "amex":
        return "3712"
    return "0000"


# Pattern 1: Discriminator-based selection (OpenAPI style)
print("=" * 80)
print("Pattern 1: Discriminator-based selection")
print("=" * 80)
disc_scenario = Scenario(
    name="discriminator_example",
    description="Using discriminator values: card payment",
    oneof_selectors={
        "method": "card",  # Matches discriminator mapping
    },
).normalize()

print("Discriminator scenario:")
print_scenario_info(disc_scenario, 1)
sample = gen.generate(disc_scenario)
print_sample(sample)
print()

# Pattern 2: Title-based nested selection
print("=" * 80)
print("Pattern 2: Title-based deep nesting")
print("=" * 80)
title_scenario = Scenario(
    name="title_deep_nest",
    description="Card -> Visa -> International -> Enhanced fraud",
    oneof_selectors={
        "method": "Card",
        "method.card_brand": "Visa",
        "method.card_brand.network": "International",
        "method.card_brand.network.fraud_check": "Enhanced",
    },
).normalize()

print("Title-based scenario:")
print_scenario_info(title_scenario, 2)
sample = gen.generate(title_scenario)
print_sample(sample)
print()

# Pattern 3: Regex selector for array items
print("=" * 80)
print("Pattern 3: Regex selectors for array items")
print("=" * 80)
regex_scenario = Scenario(
    name="array_regex",
    description="All transactions use Percentage fee structure",
    oneof_selectors={
        "method": 0,  # Card
        # Regex pattern matches transactions[0], transactions[1], etc.
        r"transactions\[\d+\]\.fee_structure": "Percentage",
    },
).normalize()

print("Regex array scenario:")
print_scenario_info(regex_scenario, 3)
sample = gen.generate(regex_scenario)
print_sample(sample)
print()

# Pattern 4: Callable selector with conditional logic
print("=" * 80)
print("Pattern 4: Callable selector with conditional logic")
print("=" * 80)


def smart_fraud_selector_demo(ctx: Context, candidates: list) -> int:
    """Select fraud level - demonstrates callable pattern.

    Note: In this example, amount override happens after oneOf selection,
    so we can't actually read it. In real use cases, pass the amount in
    default_data or read from parent schema/external config.
    """
    # For demo purposes, just select Advanced (index 1) if available
    for i, candidate in enumerate(candidates):
        title = candidate.get("title", "")
        if title in ["Enhanced", "Advanced"]:
            print(f"  → Selecting {title} fraud check (index {i})")
            return i

    print("  → Selecting Basic fraud check (index 0)")
    return 0


conditional_scenario = Scenario(
    name="conditional_selector",
    description="Callable selector with business logic",
    default_data={
        "amount": 5000,  # Set amount in default_data so it's available early
    },
    overrides={
        "payment_id": lambda ctx: f"PAY-{int(ctx.data.get('amount', 0))}",
        "currency": "USD",
    },
    oneof_selectors={
        "method": "Card",
        "method.card_brand": "Visa",
        "method.card_brand.network": "Domestic",
        "method.card_brand.network.fraud_check": smart_fraud_selector_demo,
    },
).normalize()

print("Conditional selector scenario:")
print_scenario_info(conditional_scenario, 4)
sample = gen.generate(conditional_scenario)
fraud_level = sample["method"]["card_brand"]["network"]["fraud_check"]["level"]
print(f"Amount: {sample['amount']} -> Fraud level: {fraud_level}")
print_sample(sample)
print()

# Pattern 5: Combining selectors with overrides for realistic data
print("=" * 80)
print("Pattern 5: Selectors + Overrides for Realistic Test Data")
print("=" * 80)

combined_scenario = Scenario(
    name="realistic_test_data",
    description="Generate realistic payment test data",
    default_data={
        "currency": "GBP",
        "amount": 1250.50,
    },
    overrides={
        "payment_id": lambda ctx: f"PAY-{ctx.data.get('currency', 'USD')}-{hash(str(ctx.data)) % 100000:05d}",
        # Only set specific values we care about for this test
        "method.last_four": "4242",  # Visa test card
        "method.card_brand.bin": "424242",  # Visa BIN
        "method.card_brand.network.country_code": "GB",
        "method.card_brand.network.fraud_check.risk_score": 0.15,  # Low risk
        "method.card_brand.network.fraud_check.sanctions_check": True,
    },
    oneof_selectors={
        "method": "Card",
        "method.card_brand": "Visa",
        "method.card_brand.network": "International",
        "method.card_brand.network.fraud_check": "Enhanced",
    },
).normalize()

print("Realistic test data scenario:")
print_scenario_info(combined_scenario, 5)
sample = gen.generate(combined_scenario)
print(f"\nGenerated payment: {sample['payment_id']}")
print(f"  Currency: {sample['currency']}")
print(f"  Amount: {sample['amount']}")
print(
    f"  Card: {sample['method']['card_brand']['brand'].upper()} ending in {sample['method']['last_four']}"
)
print(f"  BIN: {sample['method']['card_brand']['bin']}")
print(f"  Network: {sample['method']['card_brand']['network']['region']}")
print(
    f"  Country: {sample['method']['card_brand']['network']['country_code']}"
)
print(
    f"  Fraud Level: {sample['method']['card_brand']['network']['fraud_check']['level']}"
)
print(
    f"  Risk Score: {sample['method']['card_brand']['network']['fraud_check']['risk_score']}"
)
print("\nFull sample:")
print_sample(sample)
print()

print_separator("Summary")
print(
    f"✓ Discovered {len(sites)} variant sites across 4 nesting levels + arrays"
)
print(f"✓ Generated {len(cartesian)} cartesian scenarios (all combinations)")
print(f"✓ Generated {len(minimal_raw)} minimal scenarios (efficient coverage)")
print()
print("Advanced patterns demonstrated:")
print("  1. Discriminator-based selection (OpenAPI style)")
print("  2. Title-based deep nesting (4 levels)")
print("  3. Regex selectors for array items")
print("  4. Callable selectors with conditional logic")
print(
    "  5. Combined: selectors + overrides + pattern_overrides + default_data"
)
print()
print("Key insights:")
print("  - Nested oneOf sites are discovered automatically")
print("  - Reachability: nested sites only accessible through parent variants")
print("  - Regex patterns enable bulk array item control")
print("  - Callable selectors enable business logic in variant selection")
print("  - All features compose: mix selectors, overrides, and defaults")
print()
