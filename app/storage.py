"""Save + reload packages, findings, and clarification questions —
now including each one's reference-validation result and reviewer decisions."""

import json
from app.db import get_connection
from app.models import RequirementAnalysisResult, TestAuditResult, RTMResult
from app.validation import validate_finding, validate_clarification_question


def save_package(name: str, requirement_text: str, test_cases_text: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO packages (name, requirement_text, test_cases_text) VALUES (%s, %s, %s) RETURNING id",
        (name, requirement_text, test_cases_text),
    )
    package_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return package_id


def _save_findings(conn, package_id, findings, requirement_text, test_cases_text):
    cur = conn.cursor()
    for f in findings:
        outcome = validate_finding(f, requirement_text, test_cases_text)
        cur.execute(
            "INSERT INTO findings "
            "(package_id, level, category, test_id, source_quote, explanation, priority, source, "
            "reference_valid, validation_problems) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                package_id, f.level, f.category, f.test_id, f.source_quote, f.explanation,
                f.priority, "ai", int(outcome.reference_valid), json.dumps(outcome.problems),
            ),
        )
    cur.close()


def save_requirement_analysis(package_id: int, result: RequirementAnalysisResult,
                               requirement_text: str, test_cases_text: str) -> None:
    conn = get_connection()
    _save_findings(conn, package_id, result.findings, requirement_text, test_cases_text)
    cur = conn.cursor()
    for q in result.questions:
        outcome = validate_clarification_question(q, requirement_text)
        cur.execute(
            "INSERT INTO clarification_questions "
            "(package_id, question, requirement_ref, source, reference_valid, validation_problems) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (package_id, q.question, q.requirement_ref, "ai", int(outcome.reference_valid), json.dumps(outcome.problems)),
        )
    cur.close()
    conn.commit()
    conn.close()


def save_test_audit(package_id: int, result: TestAuditResult,
                     requirement_text: str, test_cases_text: str) -> None:
    conn = get_connection()
    _save_findings(conn, package_id, result.findings, requirement_text, test_cases_text)
    conn.commit()
    conn.close()


def save_rtm(package_id: int, result: RTMResult) -> None:
    conn = get_connection()
    cur = conn.cursor()
    for entry in result.entries:
        cur.execute(
            "INSERT INTO rtm_entries (package_id, requirement_rule, test_ids, coverage_status) "
            "VALUES (%s, %s, %s, %s)",
            (package_id, entry.requirement_rule, json.dumps(entry.test_ids), entry.coverage_status),
        )
    cur.close()
    conn.commit()
    conn.close()


def save_finding_decision(finding_id: int, reviewer_id: str, decision: str, final_text: str | None = None) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO review_decisions (finding_id, reviewer_id, decision, final_text) VALUES (%s, %s, %s, %s)",
        (finding_id, reviewer_id, decision, final_text),
    )
    cur.close()
    conn.commit()
    conn.close()


def save_question_answer(question_id: int, answer: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE clarification_questions SET answer = %s, status = 'answered' WHERE id = %s",
        (answer, question_id),
    )
    cur.close()
    conn.commit()
    conn.close()


def save_manual_finding(package_id: int, level: str, category: str, test_id: str | None,
                         source_quote: str, explanation: str, priority: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO findings "
        "(package_id, level, category, test_id, source_quote, explanation, priority, source, "
        "reference_valid, validation_problems) VALUES (%s, %s, %s, %s, %s, %s, %s, 'human', 1, '[]')",
        (package_id, level, category, test_id, source_quote, explanation, priority),
    )
    cur.close()
    conn.commit()
    conn.close()


def save_manual_question(package_id: int, question: str, requirement_ref: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO clarification_questions "
        "(package_id, question, requirement_ref, source, reference_valid, validation_problems) "
        "VALUES (%s, %s, %s, 'human', 1, '[]')",
        (package_id, question, requirement_ref),
    )
    cur.close()
    conn.commit()
    conn.close()


def load_package_review(package_id: int, requesting_user: dict) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM packages WHERE id = %s", (package_id,))
    package = cur.fetchone()

    cur.execute("SELECT * FROM findings WHERE package_id = %s", (package_id,))
    findings = cur.fetchall()

    cur.execute("SELECT * FROM clarification_questions WHERE package_id = %s", (package_id,))
    questions = cur.fetchall()

    cur.execute("SELECT * FROM rtm_entries WHERE package_id = %s", (package_id,))
    rtm_entries = cur.fetchall()

    findings_out = []
    for f in findings:
        f = dict(f)
        if requesting_user["role"] == "coordinator":
            cur.execute(
                "SELECT * FROM review_decisions WHERE finding_id = %s ORDER BY id DESC LIMIT 1",
                (f["id"],),
            )
        else:
            cur.execute(
                "SELECT * FROM review_decisions WHERE finding_id = %s AND reviewer_id = %s ORDER BY id DESC LIMIT 1",
                (f["id"], requesting_user["reviewer_id"]),
            )
        latest = cur.fetchone()
        f["decision"] = latest["decision"] if latest else "pending"
        f["final_text"] = latest["final_text"] if latest else None
        findings_out.append(f)

    cur.close()
    conn.close()
    return {
        "package": dict(package) if package else None,
        "findings": findings_out,
        "questions": [dict(q) for q in questions],
        "rtm_entries": [dict(r) for r in rtm_entries],
    }


def list_packages() -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM packages ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]