"""Streamlit page — paste a package, audit it, save it, reopen past reviews."""

import json
import requests
import streamlit as st

from loader import load_packages

API = "http://127.0.0.1:8000"

st.title("AI Test Suite Auditor")


def render_review(review: dict):
    st.subheader("Requirement")
    st.text(review["package"]["requirement_text"])
    if review["package"]["test_cases_text"]:
        st.subheader("Test Cases")
        st.text(review["package"]["test_cases_text"])

    st.subheader("Findings")
    findings = review["findings"]
    if not findings:
        st.write("No findings.")
    for f in findings:
        problems = json.loads(f["validation_problems"])
        if not f["reference_valid"]:
            st.error(f"⚠️ Reference check FAILED — {'; '.join(problems)}")
        with st.container(border=True):
            label = f"{f['level']} · {f['category']} · {f['priority']}"
            if f["test_id"]:
                label += f" · {f['test_id']}"
            st.markdown(f"**{label}**")
            st.caption(f'Quote: "{f["source_quote"]}"')
            st.write(f["explanation"])

    st.subheader("Clarification Questions")
    questions = review["questions"]
    if not questions:
        st.write("No questions.")
    for q in questions:
        problems = json.loads(q["validation_problems"])
        if not q["reference_valid"]:
            st.error(f"⚠️ Reference check FAILED — {'; '.join(problems)}")
        st.write(f"- {q['question']} (ref: {q['requirement_ref']})")
        
    if review.get("rtm_entries"):
        st.subheader("Requirements Traceability Matrix")
        for r in review["rtm_entries"]:
            test_ids = json.loads(r["test_ids"])
            status_icon = {"complete": "✅", "partial": "⚠️", "missing": "❌", "blocked_by_clarification": "🚫"}.get(r["coverage_status"], "")
            st.write(f"{status_icon} **{r['requirement_rule']}** — {r['coverage_status']} ({', '.join(test_ids) if test_ids else 'no tests'})")

tab_new, tab_reopen = st.tabs(["New Review", "Reopen Past Review"])

with tab_new:
    uploaded = st.file_uploader("Upload dev package file (.xlsx)", type=["xlsx"])
    picked = None

    if uploaded:
        try:
            packages = load_packages(uploaded)
        except Exception as e:
            st.error(f"Couldn't read that file: {e}")
            packages = []
        if packages:
            names = [p["name"] for p in packages]
            selected_name = st.selectbox("Pick a package to audit", names)
            picked = next(p for p in packages if p["name"] == selected_name)
            with st.expander("Preview parsed requirement + test cases"):
                st.text(picked["requirement_text"])
                st.text(picked["test_cases_text"])

    name = st.text_input("Package name", value=picked["name"] if picked else "Discount")
    requirement_text = st.text_area("Requirement text", value=picked["requirement_text"] if picked else "", height=200)
    test_cases_text = st.text_area("Test cases", value=picked["test_cases_text"] if picked else "", height=150)

    if st.button("Audit"):
        if not requirement_text.strip():
            st.error("Paste or upload a requirement first.")
        else:
            with st.spinner("Calling the auditor..."):
                response = requests.post(
                    f"{API}/audit-package",
                    json={"name": name, "requirement_text": requirement_text, "test_cases_text": test_cases_text},
                )
            if response.status_code == 200:
                review = response.json()
                st.success(f"Saved as package #{review['package']['id']}")
                render_review(review)
            else:
                st.error(f"Something went wrong: {response.text}")

with tab_reopen:
    packages = requests.get(f"{API}/packages").json()
    if not packages:
        st.info("No saved packages yet.")
    else:
        options = {f"#{p['id']} — {p['name']} ({p['created_at']})": p["id"] for p in packages}
        choice = st.selectbox("Pick a package", options.keys())
        if choice:
            review = requests.get(f"{API}/package/{options[choice]}").json()
            render_review(review)
