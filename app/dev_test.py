"""Manual test of analyse_requirements() against the real Discount requirement."""

from app.engine import analyse_requirements

DISCOUNT_REQUIREMENT = """REQ-01 — Discount

1. If basket total >= £100, apply a 10% discount.
2. If basket total < £100, no discount applies.
3. Maximum discount for any single order is capped at £50.
4. Discount is calculated on the pre-tax basket total."""

result = analyse_requirements(DISCOUNT_REQUIREMENT)
print(result.model_dump_json(indent=2))

from app.engine import audit_test_cases

DISCOUNT_TESTS = """TC01 | Basket £150, discount applied | Expected: Discount should be £15
TC02 | Basket £80, no discount applies | Expected: Discount should be £0
TC03 | Basket £700, discount applied | Expected: Discount should be £70
TC04 | Basket £150, discount applied | Expected: Discount should be £15"""

test_result = audit_test_cases(DISCOUNT_REQUIREMENT, DISCOUNT_TESTS)
print(test_result.model_dump_json(indent=2))

from app.engine import build_rtm

rtm_result = build_rtm(DISCOUNT_REQUIREMENT, DISCOUNT_TESTS, test_result.findings)
print(rtm_result.model_dump_json(indent=2))