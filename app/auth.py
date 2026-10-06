"""Authentication — 4 fixed accounts (two reviewers, the coordinator, and a demo account for graders).
Passwords are hashed with passlib; a simple server-side token maps to a
reviewer_id so a package filter and review_decisions queries can never be
told to act as someone else by a client-supplied value."""

import datetime
import os
import re
import secrets
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Password HASHES come from environment variables — never plaintext,
# never committed. Generate one with:
#   python -c "from app.auth import pwd_context; print(pwd_context.hash('yourpassword'))"
USERS = {
    "user1": {
        "password_hash": os.environ.get("AUTH_HASH_USER1", ""),
        "reviewer_id": "user1",  # Aruna
        "role": "reviewer",
    },
    "user2": {
        "password_hash": os.environ.get("AUTH_HASH_USER2", ""),
        "reviewer_id": "user2",  # Kaarthik
        "role": "reviewer",
    },
    "coordinator": {
        "password_hash": os.environ.get("AUTH_HASH_COORDINATOR", ""),
        "reviewer_id": "coordinator",
        "role": "coordinator",
    },
    # For graders: can run audits and review, but only on the D01-D04 samples
    # and its own DEMO runs. Never sees the held-out packages or any reviewer's
    # or the coordinator's decisions (decisions are filtered by reviewer_id).
    "demo": {
        "password_hash": os.environ.get("AUTH_HASH_DEMO", ""),
        "reviewer_id": "demo",
        "role": "demo",
    },
}

# Each reviewer's PAIRED-review package assignment, from the evaluation
# allocation table. Human-only review happens outside the app entirely.
PACKAGE_ASSIGNMENTS = {
    "user1": ["P01", "P02", "P08", "P09", "P10"],  # Aruna
    "user2": ["P03", "P04", "P05", "P06", "P07"],  # Kaarthik
}

# Demo account limits. Audits it runs are saved with a "DEMO — " name prefix;
# it can see packages whose name starts with one of these prefixes.
DEMO_VISIBLE_PREFIXES = ("D0", "DEMO")
DEMO_DAILY_AUDIT_LIMIT = int(os.environ.get("DEMO_DAILY_AUDIT_LIMIT", "20"))
_demo_runs: dict[str, int] = {}

# Set LOCK_EVAL_PACKAGES=1 to make the held-out packages P01-P10 read-only for
# everyone, so no decision, answer or added finding can change the evaluation.
LOCK_EVAL_PACKAGES = os.environ.get("LOCK_EVAL_PACKAGES", "") == "1"

# In-memory session store: token -> username. Fine for this pilot — if the
# backend restarts, reviewers just log in again; the review data itself
# always lives in the database, never here.
_sessions: dict[str, str] = {}


def verify_login(username: str, password: str) -> str | None:
    """Return a new session token if username/password match, else None."""
    user = USERS.get(username)
    if not user or not user["password_hash"]:
        return None
    if not pwd_context.verify(password, user["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    _sessions[token] = username
    return token


def get_user_from_token(token: str) -> dict | None:
    """Resolve a token back to the user record, or None if invalid."""
    username = _sessions.get(token)
    if username is None:
        return None
    return {"username": username, **USERS[username]}


def can_see_package(user: dict, package_name: str) -> bool:
    """Coordinator sees everything. A reviewer only sees packages assigned
    to them for paired review, matched by code prefix (e.g. 'P01')."""
    if user["role"] == "coordinator":
        return True
    if user["role"] == "demo":
        return package_name.startswith(DEMO_VISIBLE_PREFIXES)
    assigned = PACKAGE_ASSIGNMENTS.get(user["reviewer_id"], [])
    return any(package_name.startswith(code) for code in assigned)


def is_eval_package(package_name: str) -> bool:
    """True for the held-out evaluation packages P01-P10."""
    parts = (package_name or "").split()
    return bool(parts) and re.fullmatch(r"P(0[1-9]|10)", parts[0]) is not None


def can_write_package(user: dict, package_name: str) -> bool:
    """Writing needs read access, and the held-out packages must not be locked."""
    if not can_see_package(user, package_name):
        return False
    if LOCK_EVAL_PACKAGES and is_eval_package(package_name):
        return False
    return True


def demo_audit_allowed() -> bool:
    """Count one demo audit against today's limit; False once the limit is used."""
    today = datetime.date.today().isoformat()
    for day in list(_demo_runs):
        if day != today:
            del _demo_runs[day]
    if _demo_runs.get(today, 0) >= DEMO_DAILY_AUDIT_LIMIT:
        return False
    _demo_runs[today] = _demo_runs.get(today, 0) + 1
    return True