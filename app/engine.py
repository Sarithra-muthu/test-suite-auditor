"""LLM engine — three audit stages, with timeouts, bounded retries and
explicit failure (an exhausted retry raises AuditError; it never returns
an empty result that could be mistaken for 'no issues found')."""

import os
import time

import groq
from dotenv import load_dotenv
from groq import Groq

from app.models import RequirementAnalysisResult, TestAuditResult, RTMResult, Finding

load_dotenv()

MODEL = "openai/gpt-oss-120b"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3

_client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=TIMEOUT_SECONDS, max_retries=0)


class AuditError(Exception):
    """A stage could not produce a valid result after all attempts."""


def _run_stage(stage_name, messages, schema_name, result_model):
    schema = result_model.model_json_schema()
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            return result_model.model_validate_json(raw)
        except (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.RateLimitError,
            groq.InternalServerError,
            ValueError,  # includes pydantic ValidationError (malformed/invalid output)
        ) as e:
            last_error = e
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
    raise AuditError(f"{stage_name} failed after {MAX_ATTEMPTS} attempts ({type(last_error).__name__})")


def analyse_requirements(requirement_text: str) -> RequirementAnalysisResult:
    messages = [
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
    ]
    return _run_stage("Requirement analysis", messages, "requirement_analysis_result", RequirementAnalysisResult)


def audit_test_cases(requirement_text: str, test_cases_text: str) -> TestAuditResult:
    messages = [
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
        {"role": "user", "content": f"Requirement:\n{requirement_text}\n\nTest cases:\n{test_cases_text}"},
    ]
    return _run_stage("Test-case audit", messages, "test_audit_result", TestAuditResult)


def build_rtm(requirement_text: str, test_cases_text: str, test_findings: list[Finding]) -> RTMResult:
    known_issues = "\n".join(
        f"- {f.test_id}: {f.category} — {f.explanation}" for f in test_findings if f.test_id
    ) or "(none)"
    messages = [
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
    ]
    return _run_stage("RTM build", messages, "rtm_result", RTMResult)