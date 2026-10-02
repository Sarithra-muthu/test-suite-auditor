"""Save + reload packages, findings, and clarification questions —
now including each one's reference-validation result."""

import json
from app.db import get_connection
from app.models import RequirementAnalysisResult, TestAuditResult, RTMResult
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
            "(package_id, level, category, test_id, source_quote, explanation, priority, source, "
            "reference_valid, validation_problems) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                package_id, f.level, f.category, f.test_id, f.source_quote, f.explanation,
                f.priority, "ai", int(outcome.reference_valid), json.dumps(outcome.problems),
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
            "(package_id, question, requirement_ref, source, reference_valid, validation_problems) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (package_id, q.question, q.requirement_ref, "ai", int(outcome.reference_valid), json.dumps(outcome.problems)),
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
    rtm_entries = conn.execute("SELECT * FROM rtm_entries WHERE package_id = ?", (package_id,)).fetchall()

    findings_out = []
    for f in findings:
        f = dict(f)
        latest = conn.execute(
            "SELECT * FROM review_decisions WHERE finding_id = ? ORDER BY id DESC LIMIT 1",
            (f["id"],),
        ).fetchone()
        f["decision"] = latest["decision"] if latest else "pending"
        f["final_text"] = latest["final_text"] if latest else None
        findings_out.append(f)

    conn.close()
    return {
        "package": dict(package) if package else None,
        "findings": findings_out,
        "questions": [dict(q) for q in questions],
        "rtm_entries": [dict(r) for r in rtm_entries],
    }


def list_packages() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, created_at FROM packages ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_rtm(package_id: int, result: RTMResult) -> None:
    conn = get_connection()
    for entry in result.entries:
        conn.execute(
            "INSERT INTO rtm_entries (package_id, requirement_rule, test_ids, coverage_status) "
            "VALUES (?, ?, ?, ?)",
            (package_id, entry.requirement_rule, json.dumps(entry.test_ids), entry.coverage_status),
        )
    conn.commit()
    conn.close()

def save_finding_decision(finding_id: int, decision: str, final_text: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO review_decisions (finding_id, decision, final_text) VALUES (?, ?, ?)",
        (finding_id, decision, final_text),
    )
    conn.commit()
    conn.close()


def save_question_answer(question_id: int, answer: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE clarification_questions SET answer = ?, status = 'answered' WHERE id = ?",
        (answer, question_id),
    )
    conn.commit()
    conn.close()

def save_manual_finding(package_id: int, level: str, category: str, test_id: str | None,
                         source_quote: str, explanation: str, priority: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO findings "
        "(package_id, level, category, test_id, source_quote, explanation, priority, source, "
        "reference_valid, validation_problems) VALUES (?, ?, ?, ?, ?, ?, ?, 'human', 1, '[]')",
        (package_id, level, category, test_id, source_quote, explanation, priority),
    )
    conn.commit()
    conn.close()


def save_manual_question(package_id: int, question: str, requirement_ref: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO clarification_questions "
        "(package_id, question, requirement_ref, source, reference_valid, validation_problems) "
        "VALUES (?, ?, ?, 'human', 1, '[]')",
        (package_id, question, requirement_ref),
    )
    conn.commit()
    conn.close()