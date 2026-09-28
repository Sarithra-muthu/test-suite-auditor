"""Deterministic tests for app/validation.py — constructed Finding /
ClarificationQuestion objects only, no LLM calls."""

import pytest

from app.models import Finding, ClarificationQuestion
from app.validation import (
    extract_test_ids,
    validate_finding,
    validate_clarification_question,
    MalformedTestCasesError,
)

REQUIREMENT_TEXT = """REQ-01 — Discount

1. If basket total >= £100, apply a 10% discount.
2. If basket total < £100, no discount applies.
3. Maximum discount for any single order is capped at £50.
4. Discount is calculated on the pre-tax basket total."""

TEST_CASES_TEXT = """TC01 | Basket £150, discount applied | Expected: Discount should be £15
TC02 | Basket £80, no discount applies | Expected: Discount should be £0
TC03 | Basket £700, discount applied | Expected: Discount should be £70
TC04 | Basket £150, discount applied | Expected: Discount should be £15"""


def make_finding(**overrides):
    defaults = dict(
        level="test_case",
        category="wrong_expected_result",
        test_id="TC03",
        source_quote="TC03 | Basket £700, discount applied | Expected: Discount should be £70",
        explanation="£700 discount should be capped at £50 per rule 3.",
        priority="high",
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_existing_test_id_is_reference_valid():
    outcome = validate_finding(make_finding(test_id="TC03"), REQUIREMENT_TEXT, TEST_CASES_TEXT)
    assert outcome.reference_valid
    assert outcome.problems == []


def test_nonexistent_test_id_is_flagged():
    finding = make_finding(test_id="TC99", source_quote="TC99 | made up | Expected: nothing")
    outcome = validate_finding(finding, REQUIREMENT_TEXT, TEST_CASES_TEXT)
    assert not outcome.reference_valid
    assert any("TC99" in p for p in outcome.problems)


def test_requirement_level_finding_with_null_test_id_is_reference_valid():
    finding = make_finding(
        level="requirement",
        category="ambiguity",
        test_id=None,
        source_quote="Maximum discount for any single order is capped at £50.",
        explanation="No rule states how rounding interacts with the cap.",
    )
    outcome = validate_finding(finding, REQUIREMENT_TEXT, TEST_CASES_TEXT)
    assert outcome.reference_valid


def test_source_quote_not_verbatim_is_flagged():
    outcome = validate_finding(
        make_finding(source_quote="this text does not appear anywhere in the source"),
        REQUIREMENT_TEXT, TEST_CASES_TEXT,
    )
    assert not outcome.reference_valid
    assert any("verbatim" in p for p in outcome.problems)


def test_malformed_row_raises():
    with pytest.raises(MalformedTestCasesError):
        extract_test_ids("TC01 only two fields")


def test_duplicate_test_id_raises():
    with pytest.raises(MalformedTestCasesError):
        extract_test_ids("TC01 | a | b\nTC01 | c | d")


def test_clarification_question_valid_ref():
    q = ClarificationQuestion(question="Rounding rule?", requirement_ref="REQ-01")
    assert validate_clarification_question(q, REQUIREMENT_TEXT).reference_valid


def test_clarification_question_invalid_ref():
    q = ClarificationQuestion(question="Rounding rule?", requirement_ref="REQ-99")
    assert not validate_clarification_question(q, REQUIREMENT_TEXT).reference_valid