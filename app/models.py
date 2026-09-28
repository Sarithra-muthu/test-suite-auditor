"""Pydantic schemas — the strict shapes every LLM response gets forced into."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["requirement", "test_case"]
    category: Literal[
        "ambiguity",
        "wrong_expected_result",
        "duplicate",
        "unsupported_assumption",
        "missing_coverage",
        "other",
    ]
    test_id: Optional[str]
    source_quote: str   # verbatim text copied from the source — code-checkable
    explanation: str    # the reasoning — a human/evaluation judgment, never mechanically checked
    priority: Literal["high", "medium", "low"]


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    requirement_ref: str


class RTMEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_rule: str
    test_ids: list[str]
    coverage_status: Literal["complete", "partial", "missing", "blocked_by_clarification"]


class RequirementAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding]
    questions: list[ClarificationQuestion]


class TestAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding]


class RTMResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[RTMEntry]