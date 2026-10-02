"""FastAPI backend — wraps the engine + storage behind a small API."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.engine import analyse_requirements, audit_test_cases, build_rtm
from app.storage import (
    save_package, save_requirement_analysis, save_test_audit, save_rtm,
    save_finding_decision, save_question_answer, save_manual_finding, save_manual_question,
    load_package_review, list_packages,
)

app = FastAPI()


class AuditRequest(BaseModel):
    name: str
    requirement_text: str
    test_cases_text: str = ""


@app.post("/audit-package")
def audit_package(req: AuditRequest):
    package_id = save_package(req.name, req.requirement_text, req.test_cases_text)

    req_result = analyse_requirements(req.requirement_text)
    save_requirement_analysis(package_id, req_result, req.requirement_text, req.test_cases_text)

    test_findings = []
    if req.test_cases_text.strip():
        test_result = audit_test_cases(req.requirement_text, req.test_cases_text)
        save_test_audit(package_id, test_result, req.requirement_text, req.test_cases_text)
        test_findings = test_result.findings

        rtm_result = build_rtm(req.requirement_text, req.test_cases_text, test_findings)
        save_rtm(package_id, rtm_result)

    return load_package_review(package_id)


@app.get("/package/{package_id}")
def get_package(package_id: int):
    return load_package_review(package_id)


@app.get("/packages")
def get_packages():
    return list_packages()

class DecisionRequest(BaseModel):
    decision: str   # "accepted" or "rejected"
    final_text: str | None = None


class AnswerRequest(BaseModel):
    answer: str


@app.post("/finding/{finding_id}/decision")
def decide_finding(finding_id: int, req: DecisionRequest):
    save_finding_decision(finding_id, req.decision, req.final_text)
    return {"ok": True}


@app.post("/question/{question_id}/answer")
def answer_question(question_id: int, req: AnswerRequest):
    save_question_answer(question_id, req.answer)
    return {"ok": True}

class ManualFindingRequest(BaseModel):
    level: str
    category: str
    test_id: str | None = None
    source_quote: str
    explanation: str
    priority: str


@app.post("/package/{package_id}/finding")
def add_finding(package_id: int, req: ManualFindingRequest):
    save_manual_finding(package_id, req.level, req.category, req.test_id, req.source_quote, req.explanation, req.priority)
    return {"ok": True}

class ManualQuestionRequest(BaseModel):
    question: str
    requirement_ref: str


@app.post("/package/{package_id}/question")
def add_question(package_id: int, req: ManualQuestionRequest):
    save_manual_question(package_id, req.question, req.requirement_ref)
    return {"ok": True}