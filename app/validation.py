"""References-and-rules validation — checks a Finding's or
ClarificationQuestion's citations are real, not just correctly shaped.
No LLM call here, just plain Python.

Two things get checked: does a cited test_id/requirement_id actually
exist, and does a cited source_quote actually appear verbatim in the
source text. Whether the finding's *explanation* is actually correct is
NOT checked here — reference_valid means the citations check out, not
that the finding itself is right. That's a human/evaluation-runner call."""

import re
from dataclasses import dataclass, field

from app.models import Finding, ClarificationQuestion

REQUIREMENT_ID_PATTERN = re.compile(r"\bREQ-\d+\b")


class MalformedTestCasesError(ValueError):
    """The pasted test-cases text can't be parsed reliably — a bad row or
    a duplicate ID means the input itself can't be trusted, so we refuse
    to silently treat it as valid rather than guessing."""


@dataclass
class ValidationOutcome:
    reference_valid: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class ValidatedFinding:
    finding: Finding
    outcome: ValidationOutcome


def extract_test_ids(test_cases_text: str) -> set[str]:
    """Parse 'id | scenario | expected' lines into a set of test IDs."""
    seen: dict[str, int] = {}
    for lineno, line in enumerate(test_cases_text.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            raise MalformedTestCasesError(
                f"line {lineno} isn't in 'id | scenario | expected' format: {line!r}"
            )
        test_id = parts[0].strip()
        if not test_id:
            raise MalformedTestCasesError(f"line {lineno} has an empty test_id: {line!r}")
        if test_id in seen:
            raise MalformedTestCasesError(
                f"duplicate test_id '{test_id}' on lines {seen[test_id]} and {lineno}"
            )
        seen[test_id] = lineno
    return set(seen.keys())


def extract_requirement_ids(requirement_text: str) -> set[str]:
    """Pull every REQ-xx style ID mentioned in the requirement text."""
    return set(REQUIREMENT_ID_PATTERN.findall(requirement_text))


def validate_finding(finding: Finding, requirement_text: str, test_cases_text: str) -> ValidationOutcome:
    problems: list[str] = []

    if finding.test_id is not None:
        try:
            valid_ids = extract_test_ids(test_cases_text)
        except MalformedTestCasesError as e:
            problems.append(f"can't validate test_id — {e}")
        else:
            if finding.test_id not in valid_ids:
                problems.append(f"cites test_id '{finding.test_id}' which doesn't exist in the input")

    source_text = requirement_text if finding.level == "requirement" else test_cases_text
    if finding.source_quote.strip() and finding.source_quote.strip() not in source_text:
        problems.append("source_quote is not a verbatim match found in the source text")

    return ValidationOutcome(reference_valid=not problems, problems=problems)


def validate_clarification_question(
    question: ClarificationQuestion, requirement_text: str
) -> ValidationOutcome:
    problems: list[str] = []
    valid_ids = extract_requirement_ids(requirement_text)
    if valid_ids and question.requirement_ref not in valid_ids:
        problems.append(
            f"cites requirement_ref '{question.requirement_ref}' which doesn't appear in the requirement text"
        )
    return ValidationOutcome(reference_valid=not problems, problems=problems)


def validate_findings(
    findings: list[Finding], requirement_text: str, test_cases_text: str
) -> list[ValidatedFinding]:
    """Validate every finding and return ALL of them, tagged with their
    outcome. Never drops a failed one — a bad citation stays visible for
    debugging instead of silently vanishing."""
    return [
        ValidatedFinding(f, validate_finding(f, requirement_text, test_cases_text))
        for f in findings
    ]