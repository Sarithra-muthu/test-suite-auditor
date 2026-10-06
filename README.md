# AI Test Suite Auditor

A second pair of eyes for QA reviewers. Give it a requirement and its test suite (written by a person or by an LLM) and it:

1. flags **ambiguities and gaps in the requirement** and raises clarification questions,
2. flags **defects in the test cases**: wrong expected results, duplicates, unsupported assumptions, missing coverage,
3. builds a **Requirements Traceability Matrix (RTM)** showing which tests cover which rules,
4. lets a human reviewer **accept, reject or edit** each finding, and add anything the auditor missed.

Built as the capstone for the 100x Engineers Applied AI program (Cohort 7).

**Live app:** https://test-suite-auditor-ui.onrender.com
**Demo login:** username `demo`; the password is in the submission notes. The demo account can run audits and review the D01 samples. It cannot see the held-out packages or anyone's decisions.
Both services run on Render's always-on Starter plan, so there is no idle wake-up delay.

---

## The question behind it

Does a QA reviewer working **with** the auditor find more valid issues than the same reviewer working **alone**, and than the auditor working alone? The brief asks for a comparison of all three conditions on a real repeated task, with at least 30 runs. See [Evaluation design](#evaluation-design).

Results: **TODO: add after scoring.**

---

## Architecture

```
Render web service (UI)            Render web service (API)             Supabase
  app/ui.py            ──HTTPS──▶    FastAPI  app/main.py     ──SQL──▶   Postgres
  login, review UI                      │  auth.py (bcrypt, tokens)         packages, findings,
                                        │  engine.py ──▶ Groq               clarification_questions,
                                        │               openai/gpt-oss-120b  rtm_entries,
                                        │  validation.py (no LLM)            review_decisions
                                        └  storage.py
```

| Layer | Choice | Why |
|---|---|---|
| UI | Streamlit, hosted as a Render web service | Fast to build, enough for a findings table with buttons. Streamlit Community Cloud was tried first but the app stopped starting after a sharing change |
| API | FastAPI | Typed, works cleanly with Pydantic, and keeps secrets off the UI |
| LLM | `openai/gpt-oss-120b` on Groq, temperature 0.2 | Supports strict JSON-schema output (constrained decoding), so every response is the shape the code expects |
| Storage | Supabase Postgres | Survives restarts and redeploys. SQLite was used early on and dropped because hosted filesystems are wiped |
| Validation | Pydantic + deterministic Python checks | See below |

### The audit pipeline (`app/engine.py`)

Three plain functions, not autonomous agents. Each has its own prompt and returns a Pydantic-validated object.

1. `analyse_requirements()`: requirement-level findings and clarification questions.
2. `audit_test_cases()`: test-level findings, checked against the requirement.
3. `build_rtm()`: coverage matrix. It receives the findings from step 2 as **known facts**, so the RTM and the audit cannot disagree about the same test. A defective test still counts as *linked* to the rule it was written for, but it does not make that rule *complete*.

### Three kinds of checking, kept separate

| Layer | Checks | Done by |
|---|---|---|
| Structure | Fields, types, allowed values | Pydantic (`app/models.py`) |
| References | The cited test ID exists; the quoted evidence appears **verbatim** in the source; the requirement ref exists | `app/validation.py`, plain Python, no LLM |
| Meaning | Is the finding actually right? | Humans. Deliberately not automated |

A finding that fails the reference check is **kept and flagged** in red, never silently dropped. A passing reference check means the citation is real, not that the finding is correct.

### Failure handling

- Each Groq call has a 60 s timeout and up to 3 attempts (2 s, then 4 s backoff) for timeouts, rate limits, server errors and malformed output. Errors that retrying cannot fix, such as a bad API key, fail immediately.
- A package is saved as `incomplete` and becomes `complete` only when all three stages succeed. Otherwise it is marked `failed` or `partial`, with the reason, and is **hidden from reviewers**. A failed call can never look like "no issues found".

### Human decisions are stored separately

`review_decisions` is append-only: one row per accept, reject or edit, with the reviewer's ID. The original AI output in `findings` is never modified, so the model's output and the human's decision can always be compared.

### Access control (`app/auth.py`)

Four fixed accounts: two reviewers, a coordinator and a demo account for graders. Passwords are bcrypt-hashed and kept in environment variables. The backend resolves each session token to a reviewer ID, so the client cannot claim to be someone else.

- Reviewers see only their assigned packages and only their **own** decisions.
- Only the coordinator and the demo account can run a new audit. Only the coordinator sees everyone's decisions.
- The demo account sees only the D01 to D04 samples and its own `DEMO` runs, limited to 20 audits a day and to short inputs.
- Every endpoint that takes a package, finding or question ID checks access on the server, so a logged-in user cannot write to a package they cannot see. Setting `LOCK_EVAL_PACKAGES=1` makes the held-out packages read-only for everyone.
- This keeps the two reviewers' findings private from each other, as the evaluation design requires.

---

## Evaluation design

- **14 packages**, each with about 4 requirements and 6 to 7 test cases: 4 development packages (D01 to D04) used for building and prompt tuning, and 10 held-out evaluation packages (P01 to P10) never used for tuning. Held-out packages mix human-written and LLM-generated suites, clean and flawed suites, and ambiguous requirements.
- **3 conditions**: human-only, auditor-only, human + auditor. 10 runs each, 30 in total.
- **Mixed design**: four packages are reviewed by the same person in both human conditions and six by different people. The two groups are reported **separately**, because each has a different confound (learning effects versus reviewer differences). The mixed design does not isolate the auditor's causal contribution.
- **Frozen auditor output**: each held-out package was audited once and saved. Assisted reviewers see that saved output, never a fresh run. The frozen run used commit `cb9e47b`, `openai/gpt-oss-120b`, temperature 0.2.
- **Scoring**: recall and precision against a private reference key, evidence validity, false alarms on clean packages, and self-reported review time. Only final human-confirmed findings are scored.
- The evaluation packages and reference key are not in this repo.

---

## Run it locally

Requires Python 3.11+ (developed on 3.14) and a Postgres database such as a free Supabase project. Use Supabase's **Session pooler** connection string if your host has no IPv6.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then fill in the values
python -c "from app.db import init_db; init_db()"
uvicorn app.main:app --reload   # terminal 1
streamlit run app/ui.py         # terminal 2
```

Create a password hash for each account and put it in `.env`:

```bash
python -c "from app.auth import pwd_context; print(pwd_context.hash('choose-a-password'))"
```

Tests (no LLM calls, no database): `python -m pytest tests/ -v`. `tests/test_access.py` checks who can see and change which packages.

### Environment variables

| Name | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq API key |
| `DATABASE_URL` | Postgres connection string |
| `AUTH_HASH_USER1`, `AUTH_HASH_USER2`, `AUTH_HASH_COORDINATOR`, `AUTH_HASH_DEMO` | bcrypt hashes for the four accounts |
| `LOCK_EVAL_PACKAGES` | Optional. Set to `1` to make P01 to P10 read-only |
| `DEMO_DAILY_AUDIT_LIMIT` | Optional. Audits the demo account may run per day (default 20) |
| `API_URL` | UI service only. The backend's URL. Defaults to `http://127.0.0.1:8000` |

### Deploy

- **Render** web service: build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, with the first four variables above.
- **Streamlit UI** as a second Render web service from the same repo: build `pip install -r requirements.txt`, start `streamlit run app/ui.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`, environment variable `API_URL=https://<your-api-service>.onrender.com`. (Streamlit Community Cloud also works when it is healthy: main file `app/ui.py`, secret `API_URL`.)
- Render's network is IPv4-only, so use the Supabase **Session pooler** string, not the direct connection.

---

## Input format

One Excel sheet per package, named with the package ID. The coordinator uploads the file in the app and runs the audit once per package. A blank template is in `templates/Auditor_Input_Template.xlsx`.

```
Row 1   Package ID | Title
Row 2   (note, ignored)
Row 4   Requirement ID | Requirement
Row 5+  one requirement per row, then ONE blank row
        Test ID | Scenario | Input | Expected result
        one test per row
```

Keep IDs unique and starting with the package ID, and do not use the `|` character in any cell.

---

## Repo layout

```
app/        auth, db, engine, loader, main (API), models, storage, ui, validation
tests/      deterministic tests for the validation layer
scripts/    export_for_scoring.py (read-only export of reviewer decisions)
templates/  Auditor_Input_Template.xlsx
```

---

## Limitations

- **Small sample**: two reviewers, ten packages, one run per package. This is a pilot, not a statistically powered study.
- **LLM variance**: the same package audited twice does not return identical findings. Re-running P06 locally gave a different set of findings from the frozen run. Each package was audited once and that output was frozen.
- **Semantic correctness is not automated**: validation proves a citation is real, not that a finding is right.
- **RTM linkage is model judgment** and can over-link. Boundary-value gaps are not always caught.
- **Self-reported timing** for the assisted reviews, which is less precise than instrumented timing.
- **Generated data**: the packages were written for this study, not taken from a company's live work.
- **Hosting**: two paid Render services (UI and API), in-memory login tokens that reset on a backend restart, four hard-coded accounts, and no password reset.
- **Reviewers' source text**: the app shows evidence quotes but not the full requirement and test text, so reviewers worked from a reference workbook alongside it.
