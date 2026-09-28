"""FastAPI backend — wraps the engine + storage behind a small API."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.engine import analyse_requirements, audit_test_cases
from app.storage import (
    save_package, save_requirement_analysis, save_test_audit,
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

    if req.test_cases_text.strip():
        test_result = audit_test_cases(req.requirement_text, req.test_cases_text)
        save_test_audit(package_id, test_result, req.requirement_text, req.test_cases_text)

    return load_package_review(package_id)


@app.get("/package/{package_id}")
def get_package(package_id: int):
    return load_package_review(package_id)


@app.get("/packages")
def get_packages():
    return list_packages()