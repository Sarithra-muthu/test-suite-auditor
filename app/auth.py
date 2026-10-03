"""Reviewer authentication — 3 fixed accounts (Aruna, Kaarthik, coordinator).
Passwords are hashed with passlib; a simple server-side token maps to a
reviewer_id so a package filter and review_decisions queries can never be
told to act as someone else by a client-supplied value."""

import os
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
}

# Each reviewer's PAIRED-review package assignment, from the evaluation
# allocation table. Human-only review happens outside the app entirely.
PACKAGE_ASSIGNMENTS = {
    "user1": ["P01", "P02", "P08", "P09", "P10"],  # Aruna
    "user2": ["P03", "P04", "P05", "P06", "P07"],  # Kaarthik
}

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
    assigned = PACKAGE_ASSIGNMENTS.get(user["reviewer_id"], [])
    return any(package_name.startswith(code) for code in assigned)