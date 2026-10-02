"""LLM engine — the three audit stages, all built and wired together."""

import os
from dotenv import load_dotenv
from groq import Groq

from app.models import RequirementAnalysisResult, TestAuditResult, RTMResult, Finding

load_dotenv()  # reads GROQ_API_KEY out of .env into the environment

_client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"


def analyse_requirements(requirement_text: str) -> RequirementAnalysisResult:
    """Send a requirement to the LLM, get back ambiguity findings + clarification questions."""
    schema = RequirementAnalysisResult.model_json_schema()

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a meticulous QA reviewer. Read the requirement below and find "
                    "genuine ambiguities or gaps only — never invent a business rule the text "
                    "doesn't state. For each finding, source_quote must be an exact, verbatim "
                    "copy of the relevant text from the requirement (word for word, no "
                    "paraphrasing), and explanation is your reasoning about why it's a problem. "
                    "Raise a clear ambiguity as a requirement-level Finding (category "
                    "'ambiguity'). If it needs the requirement owner's input instead, raise it "
                    "as a ClarificationQuestion. If the requirement is fully clear, return "
                    "empty lists."
                ),
            },
            {"role": "user", "content": requirement_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "requirement_analysis_result", "strict": True, "schema": schema},
        },
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    return RequirementAnalysisResult.model_validate_json(raw)


def audit_test_cases(requirement_text: str, test_cases_text: str) -> TestAuditResult:
    """Check each test case against the requirement it belongs to."""
    schema = TestAuditResult.model_json_schema()

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a meticulous QA reviewer. You are given a requirement and its "
                    "test cases, one per line in the format 'test_id | scenario | expected'. "
                    "For each test case, check it against the requirement and flag: a wrong "
                    "expected result (category 'wrong_expected_result'), two tests that check "
                    "the same thing (category 'duplicate'), a test that assumes something the "
                    "requirement never states (category 'unsupported_assumption'), or a rule "
                    "in the requirement with no test covering it at all (category "
                    "'missing_coverage', test_id null). For each finding, source_quote must "
                    "be an exact, verbatim copy of the relevant line from the requirement or "
                    "test case (word for word), and explanation is your reasoning. Every "
                    "finding must set level to 'test_case' and test_id to the exact ID from "
                    "the input, except missing_coverage findings, which use null. If nothing "
                    "is wrong, return an empty list."
                ),
            },
            {
                "role": "user",
                "content": f"Requirement:\n{requirement_text}\n\nTest cases:\n{test_cases_text}",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "test_audit_result", "strict": True, "schema": schema},
        },
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    return TestAuditResult.model_validate_json(raw)


def build_rtm(requirement_text: str, test_cases_text: str, test_findings: list[Finding]) -> RTMResult:
    """Map every requirement rule to the tests that cover it.

    test_findings comes from audit_test_cases() — a test already flagged
    wrong_expected_result there is treated as a known fact here, not
    re-judged, so RTM and the test audit can never disagree on the same test.
    """
    schema = RTMResult.model_json_schema()

    known_issues = "\n".join(
        f"- {f.test_id}: {f.category} — {f.explanation}"
        for f in test_findings
        if f.test_id
    ) or "(none)"

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a meticulous QA reviewer building a Requirements Traceability "
                    "Matrix. You are given a requirement (with numbered/labelled rules), its "
                    "test cases ('test_id | scenario | expected'), and a list of already-"
                    "confirmed test-case issues from a prior audit — treat these as established "
                    "facts, do not re-judge them. For EVERY distinct rule in the requirement, "
                    "create one RTMEntry: requirement_rule is the rule's ID plus a short "
                    "paraphrase. test_ids must list EVERY test_id that attempts to address this "
                    "rule, even if that test is wrong, a duplicate, or based on an unsupported "
                    "assumption — a defective test is still a link, not an absence of one. "
                    "coverage_status judges whether the rule is ADEQUATELY proven, separately "
                    "from whether a test merely exists: 'complete' only if at least one linked "
                    "test is correct and not flagged as an issue; 'partial' if tests are linked "
                    "but are defective, duplicate, or only partially address the rule; 'missing' "
                    "if truly no test attempts this rule at all; 'blocked_by_clarification' if "
                    "the rule itself is too ambiguous to test until clarified."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Requirement:\n{requirement_text}\n\n"
                    f"Test cases:\n{test_cases_text}\n\n"
                    f"Known test-case issues (already confirmed, do not re-judge):\n{known_issues}"
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "rtm_result", "strict": True, "schema": schema},
        },
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    return RTMResult.model_validate_json(raw)