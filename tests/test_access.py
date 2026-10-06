"""Access-control tests for the API. No database and no LLM calls: storage and
engine are replaced with in-memory fakes, so these run anywhere.

Checks who can see and change which packages: the two reviewers, the
coordinator, and the demo account for graders."""

import importlib
import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

PASSWORDS = {"USER1": "pw-user1", "USER2": "pw-user2", "COORDINATOR": "pw-coord", "DEMO": "pw-demo"}
LOGIN = {"user1": "pw-user1", "user2": "pw-user2", "coordinator": "pw-coord", "demo": "pw-demo"}

# package id -> row
PACKAGES = {
    1: {"id": 1, "name": "D01 — Basket discount calculation", "audit_status": "complete"},
    2: {"id": 2, "name": "P01 — Employee onboarding readiness", "audit_status": "complete"},
    3: {"id": 3, "name": "P03 — Probation review scheduling", "audit_status": "complete"},
    4: {"id": 4, "name": "DEMO — D01 — a grader run", "audit_status": "complete"},
    5: {"id": 5, "name": "P10 — Equipment booking and return", "audit_status": "partial"},
    6: {"id": 6, "name": "D01 — Basket discount calculation", "audit_status": "partial"},
}
FINDING_PKG = {10: 2, 11: 3, 12: 1, 13: 5, 14: 6}   # finding id -> package id
QUESTION_PKG = {20: 2, 21: 1}                        # question id -> package id


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


@pytest.fixture(scope="module")
def api():
    mp = pytest.MonkeyPatch()
    ctx = CryptContext(schemes=["bcrypt"])
    for who, pw in PASSWORDS.items():
        mp.setenv(f"AUTH_HASH_{who}", ctx.hash(pw))
    for name in ("app.auth", "app.main", "app.storage", "app.db", "app.engine"):
        mp.delitem(sys.modules, name, raising=False)

    def no_db():
        raise RuntimeError("tests must not touch the database")

    mp.setitem(sys.modules, "app.db", _stub("app.db", get_connection=no_db))
    mp.setitem(sys.modules, "app.engine", _stub(
        "app.engine",
        analyse_requirements=lambda *a, **k: None,
        audit_test_cases=lambda *a, **k: SimpleNamespace(findings=[]),
        build_rtm=lambda *a, **k: None,
    ))
    main = importlib.import_module("app.main")
    auth = importlib.import_module("app.auth")
    yield SimpleNamespace(main=main, auth=auth, client=TestClient(main.app))
    mp.undo()
    for name in ("app.auth", "app.main", "app.storage"):
        sys.modules.pop(name, None)


@pytest.fixture
def env(api, monkeypatch):
    """Install in-memory fakes for storage and reset the demo counters."""
    m = api.main
    saved = SimpleNamespace(packages=[], decisions=[], answers=[], findings=[], questions=[])

    def fake_list(include_incomplete=False):
        return [dict(p, created_at="2026-10-06") for p in PACKAGES.values()
                if include_incomplete or p["audit_status"] == "complete"]

    def fake_save_package(name, req, tests):
        saved.packages.append(name)
        return 99

    monkeypatch.setattr(m, "list_packages", fake_list)
    monkeypatch.setattr(m, "get_package_meta", lambda pid: PACKAGES.get(pid))
    monkeypatch.setattr(m, "package_id_of_finding", lambda fid: FINDING_PKG.get(fid))
    monkeypatch.setattr(m, "package_id_of_question", lambda qid: QUESTION_PKG.get(qid))
    monkeypatch.setattr(m, "load_package_review", lambda pid, user: {"package": PACKAGES.get(pid), "findings": [], "questions": [], "rtm_entries": []})
    monkeypatch.setattr(m, "save_package", fake_save_package)
    monkeypatch.setattr(m, "save_requirement_analysis", lambda *a, **k: None)
    monkeypatch.setattr(m, "save_test_audit", lambda *a, **k: None)
    monkeypatch.setattr(m, "save_rtm", lambda *a, **k: None)
    monkeypatch.setattr(m, "set_package_status", lambda *a, **k: None)
    monkeypatch.setattr(m, "save_finding_decision", lambda fid, who, dec, txt=None: saved.decisions.append((fid, who, dec)))
    monkeypatch.setattr(m, "save_question_answer", lambda qid, ans: saved.answers.append(qid))
    monkeypatch.setattr(m, "save_manual_finding", lambda pid, *a: saved.findings.append(pid))
    monkeypatch.setattr(m, "save_manual_question", lambda pid, *a: saved.questions.append(pid))
    monkeypatch.setattr(api.auth, "LOCK_EVAL_PACKAGES", False)
    monkeypatch.setattr(api.auth, "DEMO_DAILY_AUDIT_LIMIT", 20)
    api.auth._demo_runs.clear()
    return SimpleNamespace(api=api, saved=saved, monkeypatch=monkeypatch)


def headers(api, who):
    r = api.client.post("/login", json={"username": who, "password": LOGIN[who]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


AUDIT = {"name": "D01 — Test", "requirement_text": "D01-R01: a rule.", "test_cases_text": "D01-TC01 | a test"}
FINDING = {"level": "test_case", "category": "other", "test_id": None, "source_quote": "q", "explanation": "e", "priority": "low"}


def test_requests_without_a_token_are_rejected(env):
    assert env.api.client.get("/packages").status_code == 401


def test_demo_sees_only_samples_and_its_own_runs(env):
    ids = {p["id"] for p in env.api.client.get("/packages", headers=headers(env.api, "demo")).json()}
    assert ids == {1, 4}


def test_reviewers_see_only_their_assigned_packages(env):
    api = env.api
    assert {p["id"] for p in api.client.get("/packages", headers=headers(api, "user1")).json()} == {2}
    assert {p["id"] for p in api.client.get("/packages", headers=headers(api, "user2")).json()} == {3}


def test_demo_cannot_open_held_out_or_incomplete_packages(env):
    h = headers(env.api, "demo")
    assert env.api.client.get("/package/2", headers=h).status_code == 403
    assert env.api.client.get("/package/6", headers=h).status_code == 403
    assert env.api.client.get("/package/1", headers=h).status_code == 200


def test_demo_audits_are_saved_with_a_demo_prefix(env):
    r = env.api.client.post("/audit-package", json=AUDIT, headers=headers(env.api, "demo"))
    assert r.status_code == 200
    assert env.saved.packages == ["DEMO — D01 — Test"]


def test_coordinator_keeps_the_name_and_reviewers_cannot_audit(env):
    api = env.api
    assert api.client.post("/audit-package", json=AUDIT, headers=headers(api, "coordinator")).status_code == 200
    assert env.saved.packages == ["D01 — Test"]
    assert api.client.post("/audit-package", json=AUDIT, headers=headers(api, "user1")).status_code == 403


def test_demo_daily_audit_limit(env):
    env.monkeypatch.setattr(env.api.auth, "DEMO_DAILY_AUDIT_LIMIT", 2)
    h = headers(env.api, "demo")
    codes = [env.api.client.post("/audit-package", json=AUDIT, headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_demo_input_size_limit(env):
    big = dict(AUDIT, requirement_text="x" * 7000)
    assert env.api.client.post("/audit-package", json=big, headers=headers(env.api, "demo")).status_code == 413


def test_decisions_are_limited_to_packages_the_user_may_see(env):
    api = env.api
    body = {"decision": "accepted"}
    assert api.client.post("/finding/10/decision", json=body, headers=headers(api, "user1")).status_code == 200    # P01, assigned
    assert api.client.post("/finding/11/decision", json=body, headers=headers(api, "user1")).status_code == 403    # P03, not assigned
    assert api.client.post("/finding/12/decision", json=body, headers=headers(api, "demo")).status_code == 200     # D01 sample
    assert api.client.post("/finding/10/decision", json=body, headers=headers(api, "demo")).status_code == 403     # held-out
    assert api.client.post("/finding/99/decision", json=body, headers=headers(api, "demo")).status_code == 404
    assert env.saved.decisions == [(10, "user1", "accepted"), (12, "demo", "accepted")]


def test_answers_and_additions_are_limited_the_same_way(env):
    api = env.api
    demo, user1 = headers(api, "demo"), headers(api, "user1")
    assert api.client.post("/question/20/answer", json={"answer": "a"}, headers=demo).status_code == 403
    assert api.client.post("/question/21/answer", json={"answer": "a"}, headers=demo).status_code == 200
    assert api.client.post("/package/2/finding", json=FINDING, headers=demo).status_code == 403
    assert api.client.post("/package/2/finding", json=FINDING, headers=user1).status_code == 200
    assert api.client.post("/package/1/finding", json=FINDING, headers=demo).status_code == 200
    q = {"question": "q?", "requirement_ref": "D01-R01"}
    assert api.client.post("/package/2/question", json=q, headers=demo).status_code == 403
    assert api.client.post("/package/1/question", json=q, headers=demo).status_code == 200
    assert env.saved.answers == [21] and env.saved.findings == [2, 1] and env.saved.questions == [1]


def test_incomplete_packages_cannot_be_written_to_except_by_the_coordinator(env):
    api = env.api
    body = {"decision": "accepted"}
    assert api.client.post("/finding/14/decision", json=body, headers=headers(api, "demo")).status_code == 403
    assert api.client.post("/finding/14/decision", json=body, headers=headers(api, "coordinator")).status_code == 200


def test_lock_makes_held_out_packages_read_only_for_everyone(env):
    api = env.api
    body = {"decision": "accepted"}
    env.monkeypatch.setattr(api.auth, "LOCK_EVAL_PACKAGES", True)
    assert api.client.post("/finding/10/decision", json=body, headers=headers(api, "user1")).status_code == 403
    assert api.client.post("/finding/10/decision", json=body, headers=headers(api, "coordinator")).status_code == 403
    assert api.client.post("/finding/12/decision", json=body, headers=headers(api, "demo")).status_code == 200   # samples stay editable
    assert api.client.get("/package/2", headers=headers(api, "user1")).status_code == 200                          # reading still works
