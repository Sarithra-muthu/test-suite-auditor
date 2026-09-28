"""Save + reload packages, findings, and clarification questions —
now including each one's reference-validation result."""

import json
from app.db import get_connection
from app.models import RequirementAnalysisResult, TestAuditResult
from app.validation import validate_finding, validate_clarification_question


def save_package(name: str, requirement_text: str, test_cases_text: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO packages (name, requirement_text, test_cases_text) VALUES (?, ?, ?)",
        (name, requirement_text, test_cases_text),
    )
    conn.commit()
    package_id = cur.lastrowid
    conn.close()
    return package_id


def _save_findings(conn, package_id, findings, requirement_text, test_cases_text):
    for f in findings:
        outcome = validate_finding(f, requirement_text, test_cases_text)
        conn.execute(
            "INSERT INTO findings "
            "(package_id, level, category, test_id, source_quote, explanation, priority, "
            "reference_valid, validation_problems) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                package_id, f.level, f.category, f.test_id, f.source_quote, f.explanation,
                f.priority, int(outcome.reference_valid), json.dumps(outcome.problems),
            ),
        )


def save_requirement_analysis(package_id: int, result: RequirementAnalysisResult,
                               requirement_text: str, test_cases_text: str) -> None:
    conn = get_connection()
    _save_findings(conn, package_id, result.findings, requirement_text, test_cases_text)
    for q in result.questions:
        outcome = validate_clarification_question(q, requirement_text)
        conn.execute(
            "INSERT INTO clarification_questions "
            "(package_id, question, requirement_ref, reference_valid, validation_problems) "
            "VALUES (?, ?, ?, ?, ?)",
            (package_id, q.question, q.requirement_ref, int(outcome.reference_valid), json.dumps(outcome.problems)),
        )
    conn.commit()
    conn.close()


def save_test_audit(package_id: int, result: TestAuditResult,
                     requirement_text: str, test_cases_text: str) -> None:
    conn = get_connection()
    _save_findings(conn, package_id, result.findings, requirement_text, test_cases_text)
    conn.commit()
    conn.close()


def load_package_review(package_id: int) -> dict:
    conn = get_connection()
    package = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
    findings = conn.execute("SELECT * FROM findings WHERE package_id = ?", (package_id,)).fetchall()
    questions = conn.execute(
        "SELECT * FROM clarification_questions WHERE package_id = ?", (package_id,)
    ).fetchall()
    conn.close()
    return {
        "package": dict(package) if package else None,
        "findings": [dict(f) for f in findings],
        "questions": [dict(q) for q in questions],
    }


def list_packages() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, created_at FROM packages ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]