"""FastAPI backend — wraps the engine + storage behind a small API, now with auth."""

from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel

from app.auth import verify_login, get_user_from_token, can_see_package
from app.engine import analyse_requirements, audit_test_cases, build_rtm
from app.storage import (
    save_package, save_requirement_analysis, save_test_audit, save_rtm,
    save_finding_decision, save_question_answer, save_manual_finding, save_manual_question,
    set_package_status,
    load_package_review, list_packages,
)

app = FastAPI()


def get_current_user(authorization: str = Header(default="")) -> dict:
    """Pull 'Bearer <token>' from the Authorization header, resolve it to a
    real user. Every protected endpoint depends on this — a bad or missing
    token is rejected before any handler code runs."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ")
    user = get_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/login")
def login(req: LoginRequest):
    token = verify_login(req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": token}


class AuditRequest(BaseModel):
    name: str
    requirement_text: str
    test_cases_text: str = ""


@app.post("/audit-package")
def audit_package(req: AuditRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "coordinator":
        raise HTTPException(status_code=403, detail="Only the coordinator can run a new audit")

    package_id = save_package(req.name, req.requirement_text, req.test_cases_text)  # starts 'incomplete'
    stage = "requirement analysis"
    try:
        req_result = analyse_requirements(req.requirement_text)
        save_requirement_analysis(package_id, req_result, req.requirement_text, req.test_cases_text)

        if req.test_cases_text.strip():
            stage = "test-case audit"
            test_result = audit_test_cases(req.requirement_text, req.test_cases_text)
            save_test_audit(package_id, test_result, req.requirement_text, req.test_cases_text)

            stage = "RTM build"
            rtm_result = build_rtm(req.requirement_text, req.test_cases_text, test_result.findings)
            save_rtm(package_id, rtm_result)
    except Exception as e:
        status = "failed" if stage == "requirement analysis" else "partial"
        set_package_status(package_id, status, f"{stage}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Audit {status} at {stage} ({e}). Package #{package_id} is marked {status.upper()} "
                   f"and hidden from reviewers. Run the audit again.",
        )

    set_package_status(package_id, "complete")
    return load_package_review(package_id, user)


@app.get("/package/{package_id}")
def get_package(package_id: int, user: dict = Depends(get_current_user)):
    review = load_package_review(package_id, user)
    if review["package"] is None:
        raise HTTPException(status_code=404, detail="Package not found")
    if user["role"] != "coordinator":
        if review["package"]["audit_status"] != "complete" or not can_see_package(user, review["package"]["name"]):
            raise HTTPException(status_code=403, detail="Not assigned to this package")
    return review


@app.get("/packages")
def get_packages(user: dict = Depends(get_current_user)):
    if user["role"] == "coordinator":
        return list_packages(include_incomplete=True)
    return [p for p in list_packages() if can_see_package(user, p["name"])]


class DecisionRequest(BaseModel):
    decision: str
    final_text: str | None = None


@app.post("/finding/{finding_id}/decision")
def decide_finding(finding_id: int, req: DecisionRequest, user: dict = Depends(get_current_user)):
    save_finding_decision(finding_id, user["reviewer_id"], req.decision, req.final_text)
    return {"ok": True}


class AnswerRequest(BaseModel):
    answer: str


@app.post("/question/{question_id}/answer")
def answer_question(question_id: int, req: AnswerRequest, user: dict = Depends(get_current_user)):
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
def add_finding(package_id: int, req: ManualFindingRequest, user: dict = Depends(get_current_user)):
    save_manual_finding(package_id, req.level, req.category, req.test_id, req.source_quote, req.explanation, req.priority)
    return {"ok": True}


class ManualQuestionRequest(BaseModel):
    question: str
    requirement_ref: str


@app.post("/package/{package_id}/question")
def add_question(package_id: int, req: ManualQuestionRequest, user: dict = Depends(get_current_user)):
    save_manual_question(package_id, req.question, req.requirement_ref)
    return {"ok": True}