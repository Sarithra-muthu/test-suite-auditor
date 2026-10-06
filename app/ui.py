"""Streamlit page — login, then audit/review packages depending on role."""

import csv
import io
import json
import os
import requests
import streamlit as st

from loader import load_packages

API = os.environ.get("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="AI Test Suite Auditor", layout="wide")

# ---------- Login ----------
if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.user = None

if st.session_state.token is None:
    st.title("AI Test Suite Auditor")
    st.subheader("Log in")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            r = requests.post(f"{API}/login", json={"username": username, "password": password})
            if r.status_code == 200:
                st.session_state.token = r.json()["token"]
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

AUTH = {"Authorization": f"Bearer {st.session_state.token}"}


def api_get(path):
    r = requests.get(f"{API}{path}", headers=AUTH)
    if r.status_code == 401:
        st.session_state.token = None
        st.rerun()
    return r


def api_post(path, json_body=None):
    r = requests.post(f"{API}{path}", headers=AUTH, json=json_body)
    if r.status_code == 401:
        st.session_state.token = None
        st.rerun()
    return r


# Used only to decide what to SHOW. Every real permission check
# happens on the server, on every request.
role_guess = "coordinator" if st.session_state.get("username") == "coordinator" else "reviewer"
can_audit = st.session_state.get("username") in ("coordinator", "demo")

st.title("AI Test Suite Auditor")
top = st.columns([5, 1])
top[0].caption(f"Logged in as **{st.session_state.username}**")
if top[1].button("Log out"):
    st.session_state.token = None
    st.session_state.review = None
    st.rerun()

if "review" not in st.session_state:
    st.session_state.review = None

with st.sidebar:
    if can_audit:
        st.subheader("Upload your inputs")
        if st.session_state.get("username") == "demo":
            st.caption(
                "Demo account: audits you run are saved as DEMO packages. "
                "You can also open the D01 samples under 'Open a package'."
            )
        try:
            with open("templates/Auditor_Input_Template.xlsx", "rb") as _sample:
                st.download_button(
                    "Download a sample input file", _sample.read(),
                    file_name="Auditor_Input_Template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        except FileNotFoundError:
            pass
        uploaded = st.file_uploader("Requirements + test cases (.xlsx)", type=["xlsx"])
        picked = None

        if uploaded:
            try:
                packages = load_packages(uploaded)
            except Exception as e:
                st.error(f"Couldn't read that file: {e}")
                packages = []
            if packages:
                names = [p["name"] for p in packages]
                selected_name = st.selectbox("Pick a package", names)
                picked = next(p for p in packages if p["name"] == selected_name)
                st.caption(f"{picked['n_requirements']} requirements · {picked['n_tests']} test cases")
                with st.expander("Preview source inputs"):
                    st.text(picked["requirement_text"])
                    st.text(picked["test_cases_text"])

        name = st.text_input("Package name", value=picked["name"] if picked else "Discount")

        with st.expander("Edit inputs (advanced)"):
            requirement_text = st.text_area(
                "Requirement text", value=picked["requirement_text"] if picked else "", height=150,
            )
            test_cases_text = st.text_area(
                "Test cases", value=picked["test_cases_text"] if picked else "", height=100,
            )

        if st.button("Run audit", type="primary", use_container_width=True):
            if not requirement_text.strip():
                st.error("Paste or upload a requirement first.")
            else:
                with st.spinner("Calling the auditor..."):
                    response = api_post(
                        "/audit-package",
                        {"name": name, "requirement_text": requirement_text, "test_cases_text": test_cases_text},
                    )
                if response.status_code == 200:
                    st.session_state.review = response.json()
                    st.success(f"Saved as package #{st.session_state.review['package']['id']}")
                else:
                    try:
                        msg = response.json().get("detail", response.text)
                    except ValueError:
                        msg = response.text
                    st.error(f"Audit did not complete: {msg}")

        st.divider()

    st.subheader("Open a package")
    pk_resp = api_get("/packages")
    if pk_resp.status_code != 200:
        st.error(f"Couldn't load packages: {pk_resp.text}")
        past_packages = []
    else:
        past_packages = pk_resp.json()

    if not past_packages:
        st.info("No packages assigned to you yet." if not can_audit else "No packages yet — run an audit above.")
    else:
        options = {
            f"#{p['id']} — {p['name']} ({p['created_at']})"
            + ("" if p.get("audit_status", "complete") == "complete" else f" ⚠️ {p['audit_status'].upper()}"): p["id"]
            for p in past_packages
        }
        choice = st.selectbox("Pick a package", ["—"] + list(options.keys()))
        if choice != "—":
            resp = api_get(f"/package/{options[choice]}")
            if resp.status_code == 200:
                st.session_state.review = resp.json()
            else:
                st.error(f"Couldn't open that package: {resp.text}")


def reload_current_review():
    pid = st.session_state.review["package"]["id"]
    resp = api_get(f"/package/{pid}")
    if resp.status_code == 200:
        st.session_state.review = resp.json()


review = st.session_state.review

if review is None:
    st.info("Pick a package from the sidebar to get started.")
    st.stop()

st.caption(f"{review['package']['name']}")

if review["package"].get("audit_status", "complete") != "complete":
    st.error(
        f"⚠️ This audit is {review['package']['audit_status'].upper()}: "
        f"{review['package'].get('audit_note') or ''}. Do not use it for review. Run the audit again."
    )

st.header("Review the auditor's findings")
st.caption("Check the evidence. You decide what belongs in the final review.")

total = len(review["findings"])
reviewed = sum(1 for f in review["findings"] if f["decision"] != "pending")
st.caption(f"{reviewed} of {total} findings reviewed (showing your own decisions)")

tab_findings, tab_clarify, tab_rtm, tab_report = st.tabs(
    ["Findings", "Clarifications", "Coverage / RTM", "Report"]
)

with tab_findings:
    if not review["findings"]:
        st.write("No findings.")
    for f in review["findings"]:
        with st.container(border=True):
            top_row = st.columns([4, 1])
            label = f"{f['category'].replace('_', ' ').title()}"
            if f["test_id"]:
                label += f" · {f['test_id']}"
            top_row[0].markdown(f"**{label}**")
            status_color = {"accepted": "green", "rejected": "red", "pending": "gray"}[f["decision"]]
            top_row[1].markdown(f":{status_color}[{f['decision'].title()}]")
            if f.get("source") == "human":
                st.caption("👤 Added by a reviewer")

            problems = json.loads(f["validation_problems"])
            if not f["reference_valid"]:
                st.error(f"⚠️ Reference check FAILED — {'; '.join(problems)}")

            st.caption(f'Evidence: "{f["source_quote"]}"')
            st.write(f["explanation"])

            if f["decision"] == "accepted" and f["final_text"] and f["final_text"] != f["explanation"]:
                st.info(f"✏️ Your edited version (saved): {f['final_text']}")
            elif f["decision"] == "rejected" and f["final_text"]:
                st.warning(f"🚫 Rejection reason: {f['final_text']}")

            reason_key = f"reason_{f['id']}_{f['decision']}"
            if f["decision"] != "rejected":
                st.text_input("Rejection reason (optional)", key=reason_key, placeholder="Why are you rejecting this?")

            editing_key = f"editing_{f['id']}"
            if editing_key not in st.session_state:
                st.session_state[editing_key] = False

            accept_type = "primary" if f["decision"] == "accepted" else "secondary"
            reject_type = "primary" if f["decision"] == "rejected" else "secondary"

            b1, b2, b3 = st.columns(3)
            if b1.button("✅ Accept", key=f"acc_{f['id']}", type=accept_type, use_container_width=True):
                st.session_state[editing_key] = False
                r = api_post(f"/finding/{f['id']}/decision", {"decision": "accepted"})
                if r.status_code == 200:
                    reload_current_review(); st.rerun()
                else:
                    st.error(f"Save failed: {r.text}")
            if b2.button("❌ Reject", key=f"rej_{f['id']}", type=reject_type, use_container_width=True):
                st.session_state[editing_key] = False
                reason = st.session_state.get(reason_key, "")
                r = api_post(f"/finding/{f['id']}/decision", {"decision": "rejected", "final_text": reason or None})
                if r.status_code == 200:
                    reload_current_review(); st.rerun()
                else:
                    st.error(f"Save failed: {r.text}")
            if b3.button("✏️ Edit & accept", key=f"editbtn_{f['id']}", use_container_width=True):
                st.session_state[editing_key] = True
                st.rerun()

            if st.session_state[editing_key]:
                with st.container(border=True):
                    st.caption("Edit the finding before accepting")
                    edit_text = st.text_area(
                        "Final finding / reason",
                        value=f["final_text"] or f["explanation"],
                        key=f"edittext_{f['id']}", height=100,
                    )
                    e1, e2 = st.columns(2)
                    if e1.button("💾 Save edit & accept", key=f"saveedit_{f['id']}", type="primary", use_container_width=True):
                        r = api_post(f"/finding/{f['id']}/decision", {"decision": "accepted", "final_text": edit_text})
                        if r.status_code == 200:
                            st.session_state[editing_key] = False
                            reload_current_review(); st.rerun()
                        else:
                            st.error(f"Save failed: {r.text}")
                    if e2.button("Cancel", key=f"canceledit_{f['id']}", use_container_width=True):
                        st.session_state[editing_key] = False
                        st.rerun()

    st.divider()
    with st.expander("➕ Add a finding the auditor missed"):
        with st.form(key="add_finding_form", clear_on_submit=True):
            level = st.selectbox("Level", ["requirement", "test_case"])
            category = st.selectbox(
                "Category",
                ["ambiguity", "wrong_expected_result", "duplicate", "unsupported_assumption", "missing_coverage", "other"],
            )
            test_id = st.text_input("Test ID (leave blank for a requirement-level finding)")
            source_quote = st.text_area("Source quote (copy the exact relevant text)", height=60)
            explanation = st.text_area("Explanation", height=80)
            priority = st.selectbox("Priority", ["high", "medium", "low"])
            if st.form_submit_button("Add finding"):
                r = api_post(
                    f"/package/{review['package']['id']}/finding",
                    {
                        "level": level, "category": category, "test_id": test_id or None,
                        "source_quote": source_quote, "explanation": explanation, "priority": priority,
                    },
                )
                if r.status_code == 200:
                    reload_current_review(); st.rerun()
                else:
                    st.error(f"Add failed: {r.text}")

with tab_clarify:
    if not review["questions"]:
        st.write("No clarification questions.")
    for q in review["questions"]:
        with st.container(border=True):
            st.markdown(f"**{q['question']}**")
            st.caption(f"ref: {q['requirement_ref']} · status: {q['status']}")
            if q.get("source") == "human":
                st.caption("👤 Added by a reviewer")
            answer = st.text_area("Answer", value=q["answer"] or "", key=f"ans_{q['id']}", height=60)
            if st.button("Save answer", key=f"save_ans_{q['id']}"):
                r = api_post(f"/question/{q['id']}/answer", {"answer": answer})
                if r.status_code == 200:
                    reload_current_review()
                    st.toast("✅ Answer saved")
                    st.rerun()
                else:
                    st.error(f"Save failed: {r.text}")

    st.divider()
    with st.expander("➕ Add a clarification question"):
        with st.form(key="add_question_form", clear_on_submit=True):
            question = st.text_area("Question", height=80)
            requirement_ref = st.text_input("Requirement ref (e.g. D01-R03)")
            if st.form_submit_button("Add question"):
                r = api_post(
                    f"/package/{review['package']['id']}/question",
                    {"question": question, "requirement_ref": requirement_ref},
                )
                if r.status_code == 200:
                    reload_current_review(); st.rerun()
                else:
                    st.error(f"Add failed: {r.text}")

with tab_rtm:
    entries = review.get("rtm_entries", [])
    if not entries:
        st.write("No RTM yet — RTM is only built when test cases are included.")
    else:
        icons = {"complete": "✅", "partial": "⚠️", "missing": "❌", "blocked_by_clarification": "🚫"}
        rows = [
            {
                "": icons.get(r["coverage_status"], ""),
                "Requirement Rule": r["requirement_rule"],
                "Coverage": r["coverage_status"].replace("_", " ").title(),
                "Linked Tests": ", ".join(json.loads(r["test_ids"])) or "—",
            }
            for r in entries
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True)

with tab_report:
    st.subheader("Findings")
    findings_rows = [
        {
            "Level": f["level"], "Category": f["category"], "Test ID": f["test_id"] or "—",
            "Decision": f["decision"], "Source": f.get("source", "ai"),
            "Explanation": f["explanation"],
            "Human text (edit/reject reason)": f["final_text"] or "—",
        }
        for f in review["findings"]
    ]
    st.dataframe(findings_rows, hide_index=True, use_container_width=True)

    st.subheader("Clarification Questions")
    question_rows = [
        {"Question": q["question"], "Ref": q["requirement_ref"], "Status": q["status"], "Answer": q["answer"] or "—"}
        for q in review["questions"]
    ]
    st.dataframe(question_rows, hide_index=True, use_container_width=True)

    st.subheader("Coverage / RTM")
    entries = review.get("rtm_entries", [])
    if entries:
        icons = {"complete": "✅", "partial": "⚠️", "missing": "❌", "blocked_by_clarification": "🚫"}
        rtm_rows = [
            {
                "": icons.get(r["coverage_status"], ""),
                "Requirement Rule": r["requirement_rule"],
                "Coverage": r["coverage_status"].replace("_", " ").title(),
                "Linked Tests": ", ".join(json.loads(r["test_ids"])) or "—",
            }
            for r in entries
        ]
        st.dataframe(rtm_rows, hide_index=True, use_container_width=True)
    else:
        st.write("No RTM for this package.")

    st.divider()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Level", "Category", "Test ID", "Decision", "Source", "Source Quote", "Final Text"])
    writer.writeheader()
    for f in review["findings"]:
        writer.writerow({
            "Level": f["level"], "Category": f["category"], "Test ID": f["test_id"] or "",
            "Decision": f["decision"], "Source": f.get("source", "ai"),
            "Source Quote": f["source_quote"], "Final Text": f["final_text"] or f["explanation"],
        })
    st.download_button(
        "⬇️ Download final findings (CSV)", data=output.getvalue(),
        file_name=f"{review['package']['name']}_findings.csv", mime="text/csv",
    )