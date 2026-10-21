# Phrase Matcher on Azure Functions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python service that returns the closest of 15 predefined phrases to a user phrase, deployed first to Azure Functions and then to Azure App Service, with tests at each stage.

**Architecture:** One pure-Python module (`matcher.py`, no Azure imports) holds all logic. A thin Azure Functions HTTP trigger (`functions/function_app.py`) and a thin Flask app (`app_service/app.py`) call it. Tests run against `matcher.py` with pytest, no Azure needed.

**Tech Stack:** Python 3.11, `difflib` (standard library), Azure Functions Python v2 model (`azure-functions`), Flask and gunicorn for App Service, pytest, Azure Functions Core Tools v4, Azure CLI.

**Spec:** `docs/superpowers/specs/2026-10-21-azure-phrase-matcher-design.md`

## Global Constraints

- Python 3.11 on the developer machine and on both Azure targets.
- Matching uses `difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()`, rounded to 2 decimals. No minimum-score threshold.
- `normalize`: lowercase, strip, collapse internal whitespace to single spaces.
- Ties go to the earlier phrase in the list.
- Functions route: `POST /api/match`, `auth_level` ANONYMOUS. App Service route: `POST /match`.
- Success body: `{"match": <str>, "score": <float>}` with status 200.
- Error bodies: `{"error": <str>}`. Invalid JSON, or missing/blank/non-string `phrase`, gives 400. Unexpected exceptions give a generic 500 and log the stack trace.
- Error messages: invalid JSON → `Request body must be valid JSON.`; bad phrase → `'phrase' must be a non-empty string.`; server error → `Internal server error.`
- Functions plan: Linux, Python 3.11, Consumption plan, Functions runtime v4.
- App Service plan: Linux, Python 3.11, B1 SKU.
- Git: the project is not a repository. Commit steps run only after `git init` is approved. Until then, skip them.

## Review Focus

1. Blank or whitespace-only `phrase` → 400, not a match against an empty string.
2. Non-string `phrase` (number, `null`, list, object) → 400, not a crash.
3. Malformed JSON body → 400 with the JSON error message, not 500.
4. Accented or non-Latin text (for example `café`) matches without error.
5. Very long input (10,000 characters) returns a result without error or timeout.

Each line is pinned by a test in the owning task: 1, 2 and 5 in Task 2; 3 in Task 3 and Task 5 (manual, with the expected output); 4 in Task 2.

---

### Task 1: Project Skeleton and Phrase Data

**Files:**
- Create: `functions/phrases.json`
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `.venv` (local virtual environment, not committed)

**Interfaces:**
- Consumes: nothing.
- Produces: `functions/phrases.json` is a JSON array of 15 non-empty strings, used by `load_phrases` in Task 2. `tests/conftest.py` puts `functions/` on `sys.path` so tests can `import matcher`.

- [ ] **Step 1: Create the virtual environment and install dev tools**

Run: `python -m venv .venv` then `.venv\Scripts\activate` then `pip install pytest`
Expected: `pip show pytest` prints a version.

- [ ] **Step 2: Create `requirements-dev.txt`**

Content: a single line `pytest`.

- [ ] **Step 3: Create `functions/phrases.json`**

A JSON array of exactly 15 distinct strings, all lowercase, for example `"hello world"`, `"good morning"`, `"how are you"`, `"thank you very much"`, `"see you tomorrow"`. Keep each phrase under 40 characters.

- [ ] **Step 4: Create `tests/conftest.py`**

Insert the absolute path of `functions/` (relative to the file: `Path(__file__).parent.parent / "functions"`) at the front of `sys.path`.

- [ ] **Step 5: Verify pytest runs with no tests**

Run: `pytest`
Expected: `no tests ran` with exit code 5. No import errors.

- [ ] **Step 6: Commit** (skip until git is initialized)

```bash
git add requirements-dev.txt functions/phrases.json tests/conftest.py
git commit -m "chore: add project skeleton and phrase data"
```

---

### Task 2: Matching Logic (`matcher.py`)

**Files:**
- Create: `functions/matcher.py`
- Test: `tests/test_matcher.py`

**Interfaces:**
- Consumes: `functions/phrases.json` (Task 1).
- Produces, all in `matcher.py`:
  - `normalize(text: str) -> str`
  - `load_phrases(path: str | Path) -> list[str]`: raises `ValueError` if the file is not a non-empty JSON array of strings.
  - `find_closest(query: str, phrases: list[str]) -> tuple[str, float]`: score rounded to 2 decimals; ties go to the earlier phrase.
  - `extract_phrase(payload: object) -> str`: returns the stripped `phrase` value. Raises `ValueError("'phrase' must be a non-empty string.")` when `payload` is not a dict, has no `phrase`, or the value is not a string or is blank after stripping. Used by both HTTP layers in Tasks 3 and 5.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from matcher import normalize, load_phrases, find_closest, extract_phrase


def test_normalize_lowercases_and_collapses_whitespace():
    assert normalize("  Hello   WORLD \n") == "hello world"


def test_normalize_blank_is_empty():
    assert normalize("   ") == ""


def test_find_closest_exact_match_scores_one():
    assert find_closest("hello world", ["goodbye", "hello world"]) == ("hello world", 1.0)


def test_find_closest_picks_near_miss():
    phrases = ["good morning", "good night", "see you soon"]
    assert find_closest("gud mornin", phrases)[0] == "good morning"


def test_find_closest_is_deterministic():
    phrases = ["alpha", "alphas", "beta"]
    assert find_closest("alph", phrases) == find_closest("alph", phrases)


def test_find_closest_tie_returns_earlier_phrase():
    # "aa" scores 0.5 against both "ab" and "ba"
    assert find_closest("aa", ["ab", "ba"])[0] == "ab"


def test_find_closest_handles_accented_text():  # Review Focus 4
    assert find_closest("café", ["cafe", "tea"])[0] == "cafe"


def test_find_closest_handles_very_long_input():  # Review Focus 5
    phrase, score = find_closest("x" * 10_000, ["hello", "world"])
    assert phrase in ["hello", "world"]
    assert 0.0 <= score <= 1.0


def test_load_phrases_reads_json_array(tmp_path):
    f = tmp_path / "p.json"
    f.write_text('["one", "two"]', encoding="utf-8")
    assert load_phrases(f) == ["one", "two"]


@pytest.mark.parametrize("content", ["[]", '["ok", 5]', '{"a": 1}'])
def test_load_phrases_rejects_bad_content(tmp_path, content):
    f = tmp_path / "p.json"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_phrases(f)


@pytest.mark.parametrize("payload", [{"phrase": "  hi  "}])
def test_extract_phrase_returns_stripped_value(payload):
    assert extract_phrase(payload) == "hi"


@pytest.mark.parametrize("payload", [
    {"phrase": "   "},   # Review Focus 1
    {"phrase": 5},       # Review Focus 2
    {"phrase": None},    # Review Focus 2
    {"phrase": ["hi"]},  # Review Focus 2
    {},
    None,
    ["hi"],
])
def test_extract_phrase_rejects_bad_input(payload):
    with pytest.raises(ValueError, match="non-empty string"):
        extract_phrase(payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_matcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'matcher'`

- [ ] **Step 3: Implement the four functions in `functions/matcher.py`**

Use `difflib.SequenceMatcher` as in Global Constraints. For `find_closest`, loop over phrases and keep the first one with the highest score (use `>`, not `>=`, to keep ties on the earlier phrase). Use `json` and `Path.read_text(encoding="utf-8")` for `load_phrases`. No Azure imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_matcher.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Verify `phrases.json` loads with the real data**

Run: `python -c "import sys; sys.path.insert(0,'functions'); from matcher import load_phrases; p=load_phrases('functions/phrases.json'); print(len(p))"`
Expected: `15`

- [ ] **Step 6: Commit** (skip until git is initialized)

```bash
git add functions/matcher.py tests/test_matcher.py
git commit -m "feat: add phrase matching logic with tests"
```

---

### Task 3: Azure Functions App and Local Run

**Files:**
- Create: `functions/function_app.py`
- Create: `functions/host.json`
- Create: `functions/local.settings.json`
- Create: `functions/requirements.txt`
- Create: `functions/.funcignore`

**Interfaces:**
- Consumes: `matcher.load_phrases`, `matcher.find_closest`, `matcher.extract_phrase` (Task 2); `functions/phrases.json` (Task 1).
- Produces: HTTP route `POST /api/match` on the Functions host.

- [ ] **Step 1: Install the Azure Functions tools**

Run: `winget install Microsoft.Azure.FunctionsCoreTools` then `winget install Microsoft.AzureCLI`. Open a new terminal.
Expected: `func --version` prints a 4.x version and `az --version` prints a version.

- [ ] **Step 2: Create `functions/requirements.txt`**

Install with `pip install azure-functions` (inside `.venv`), then write the line `azure-functions==<installed version>` using the version `pip show azure-functions` prints.

- [ ] **Step 3: Create `functions/host.json`**

Values: `"version": "2.0"` and the extension bundle `{"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"}`.

- [ ] **Step 4: Create `functions/local.settings.json`**

Values: `"IsEncrypted": false`, `"Values": {"AzureWebJobsStorage": "", "FUNCTIONS_WORKER_RUNTIME": "python"}`. Add this file to `.funcignore` so it is never deployed.

- [ ] **Step 5: Create `functions/.funcignore`**

Lines: `.venv`, `local.settings.json`, `__pycache__`, `*.pyc`.

- [ ] **Step 6: Implement `functions/function_app.py`**

- `app = func.FunctionApp()`
- Load phrases once at module level from `Path(__file__).parent / "phrases.json"`.
- One function `match(req: func.HttpRequest) -> func.HttpResponse` decorated with `@app.route(route="match", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)`.
- Flow: `req.get_json()` (catch `ValueError` → 400 with the invalid JSON message) → `extract_phrase` (catch `ValueError` → 400 with its message) → `find_closest` → 200 JSON. Wrap the rest in a broad `except Exception` that calls `logging.exception` and returns 500 with the generic message.

- [ ] **Step 7: Run the Functions host locally**

Run from `functions/`: `func start`
Expected: the console lists `match: [POST] http://localhost:7071/api/match`.

- [ ] **Step 8: Verify the success case**

Run in a second terminal: `curl.exe -X POST http://localhost:7071/api/match -H "Content-Type: application/json" -d "{\"phrase\": \"helo wrld\"}"`
Expected: `{"match": "hello world", "score": ...}` with a score between 0 and 1 (the exact score may vary).

- [ ] **Step 9: Verify the error cases (Review Focus 1, 2, 3)**

| Request body | Expected status | Expected body |
|---|---|---|
| `{"phrase": "   "}` | 400 | `{"error": "'phrase' must be a non-empty string."}` |
| `{"phrase": 5}` | 400 | same as above |
| `{"phrase": "hi"` (malformed) | 400 | `{"error": "Request body must be valid JSON."}` |

Check status with `curl.exe -s -o NUL -w "%{http_code}"` and the body with a plain `curl.exe` call.

- [ ] **Step 10: Commit** (skip until git is initialized)

```bash
git add functions/
git commit -m "feat: add HTTP-triggered Azure Function for phrase matching"
```

---

### Task 4: App Service Flask App and Local Run

**Files:**
- Create: `app_service/app.py`
- Create: `app_service/matcher.py` (copy of `functions/matcher.py`)
- Create: `app_service/phrases.json` (copy of `functions/phrases.json`)
- Create: `app_service/requirements.txt`

**Interfaces:**
- Consumes: `matcher.load_phrases`, `matcher.find_closest`, `matcher.extract_phrase` (Task 2).
- Produces: `app.py` exposes a Flask object named `app`, served at `POST /match`.

- [ ] **Step 1: Copy the shared files**

Copy `functions/matcher.py` and `functions/phrases.json` into `app_service/` (spec §8: copies, not links).
Verify: `Compare-Object (Get-Content functions\matcher.py) (Get-Content app_service\matcher.py)` prints nothing.

- [ ] **Step 2: Create `app_service/requirements.txt`**

Install with `pip install flask gunicorn` (inside `.venv`), then write lines `flask==<version>` and `gunicorn==<version>` using the installed versions. gunicorn runs on Azure Linux only; it is not needed to run locally on Windows.

- [ ] **Step 3: Implement `app_service/app.py`**

- `app = Flask(__name__)`
- Load phrases once at module level from `Path(__file__).parent / "phrases.json"`.
- `@app.post("/match")` function `match()`.
- Flow: `request.get_json(silent=True)` returns `None` on invalid JSON → 400 with the invalid JSON message → `extract_phrase` (catch `ValueError` → 400) → `find_closest` → `jsonify` 200. Broad `except Exception` logs and returns 500 with the generic message.

- [ ] **Step 4: Run locally**

Run from `app_service/`: `python -m flask --app app run --port 8000`
Expected: `Running on http://127.0.0.1:8000`

- [ ] **Step 5: Verify success and error cases**

Run the same three checks as Task 3 Steps 8 and 9, using `http://localhost:8000/match`.
Expected: identical status codes and bodies to the Functions version.

- [ ] **Step 6: Commit** (skip until git is initialized)

```bash
git add app_service/
git commit -m "feat: add Flask app for App Service comparison"
```

---

### Task 5: Deploy to Azure Functions and Test the Endpoint

**Files:**
- Modify: none. Uses `functions/` as is.

**Interfaces:**
- Consumes: the Functions app from Task 3.
- Produces: a public URL `https://<FUNC_APP>.azurewebsites.net/api/match`.

**Before running this task:** the steps below create paid Azure resources in your subscription. Confirm you want them created before executing.

- [ ] **Step 1: Sign in and set variables**

Run: `az login`. Then set these variables (example values; choose unique names):

```powershell
$RG = "rg-phrase-matcher"
$LOC = "eastus"
$STORAGE = "stphrasematcher<random digits>"   # lowercase letters and digits, 3–24 chars, globally unique
$FUNC_APP = "func-phrase-matcher-<random digits>"   # globally unique
```

- [ ] **Step 2: Create the resource group and storage account**

Run: `az group create -n $RG -l $LOC` then `az storage account create -n $STORAGE -g $RG -l $LOC --sku Standard_LRS`
Expected: both commands return JSON with `"provisioningState": "Succeeded"`.

- [ ] **Step 3: Create the Function App**

Run: `az functionapp create -g $RG -n $FUNC_APP --storage-account $STORAGE --consumption-plan-location $LOC --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux`
Expected: JSON with `"state": "Running"`.

- [ ] **Step 4: Publish the code**

Run from `functions/`: `func azure functionapp publish $FUNC_APP --python`
Expected: the output ends with `Deployment successful` and lists `match - [POST] https://<FUNC_APP>.azurewebsites.net/api/match`.

- [ ] **Step 5: Test the deployed endpoint**

Run: `curl.exe -X POST https://$FUNC_APP.azurewebsites.net/api/match -H "Content-Type: application/json" -d "{\"phrase\": \"helo wrld\"}"`
Expected: `{"match": "hello world", "score": ...}`. The first call may be slow (cold start).

Then repeat the three error cases from Task 3 Step 9 against the deployed URL. Expected: the same status codes and bodies.

- [ ] **Step 6: Check logs if a call fails**

Run: `func azure functionapp logstream $FUNC_APP`
Expected: request and exception lines appear while you repeat the failing call.

---

### Task 6: Deploy to Azure App Service and Test the Endpoint

**Files:**
- Modify: none. Uses `app_service/` as is.

**Interfaces:**
- Consumes: the Flask app from Task 4.
- Produces: a public URL `https://<WEB_APP>.azurewebsites.net/match`.

**Before running this task:** confirm the B1 plan cost is acceptable, since it is billed while it exists.

- [ ] **Step 1: Set variables**

```powershell
$WEB_APP = "app-phrase-matcher-<random digits>"   # globally unique
$PLAN = "plan-phrase-matcher"
```

- [ ] **Step 2: Create the App Service plan and web app**

Run: `az appservice plan create -g $RG -n $PLAN --is-linux --sku B1` then `az webapp create -g $RG -p $PLAN -n $WEB_APP --runtime "PYTHON:3.11"`
Expected: both return JSON with `"state": "Running"` for the web app.

- [ ] **Step 3: Configure the startup command and build on deploy**

Run: `az webapp config set -g $RG -n $WEB_APP --startup-file "gunicorn --bind=0.0.0.0:8000 app:app"` and `az webapp config appsettings set -g $RG -n $WEB_APP --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true`
Expected: both return JSON. The second setting makes Azure install `requirements.txt` on deploy.

- [ ] **Step 4: Package and deploy**

From the project root in PowerShell:

```powershell
Compress-Archive -Path app_service\* -DestinationPath app_service.zip -Force
az webapp deploy -g $RG -n $WEB_APP --type zip --src-path app_service.zip
```

Expected: the deploy command finishes with a JSON status of `"status": 4` or `"Deployment successful"`.

- [ ] **Step 5: Test the deployed endpoint**

Run: `curl.exe -X POST https://$WEB_APP.azurewebsites.net/match -H "Content-Type: application/json" -d "{\"phrase\": \"helo wrld\"}"`
Expected: `{"match": "hello world", "score": ...}`.

Then repeat the three error cases. Expected: the same status codes and bodies as Functions.

- [ ] **Step 6: Check logs if a call fails**

Run: `az webapp log tail -g $RG -n $WEB_APP`
Expected: gunicorn and request lines appear while you repeat the failing call.

---

### Task 7: README and Comparison

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the commands and URLs from Tasks 3–6, and the comparison table in spec §11.
- Produces: the user-facing guide for the project.

- [ ] **Step 1: Write the README**

Sections, in order: project layout (the tree from spec §3); local setup (venv, `pip install -r requirements-dev.txt`, `pip install -r functions/requirements.txt`); running tests (`pytest`); running locally (Functions with `func start`, App Service with flask); the curl checklist for both local and deployed URLs; deploying to Functions (Task 5 commands); deploying to App Service (Task 6 commands); the "Why two copies of matcher.py" note from spec §8; the comparison table from spec §11.

- [ ] **Step 2: Verify the comparison against Microsoft Learn**

Use the Microsoft Learn MCP tools to confirm the Consumption plan scale-to-zero and cold-start statements and the App Service B1 billing statement. Correct the table in the README if any cell is wrong.

- [ ] **Step 3: Verify the README commands**

Check that each command in the README matches the commands used in Tasks 1–6. Expected: no differences in variable names or flags.

- [ ] **Step 4: Commit** (skip until git is initialized)

```bash
git add README.md
git commit -m "docs: add README with setup, deploy, and comparison"
```

---

## Self-Review Notes

- **Spec coverage:** §3 layout → Tasks 1–4 and 7; §4.1 matcher → Task 2; §4.2 Functions → Task 3; §4.3 App Service → Task 4; §5 API and errors → Tasks 3, 4 (checked in 3, 4, 5, 6); §6 data flow → Tasks 3, 4; §7 error handling → Tasks 3, 4; §8 duplication → Task 4 Step 1; §9 testing → Tasks 2, 3, 4, 5, 6; §10 deployment → Tasks 5, 6; §11 comparison → Task 7; §12 open points → gated by the "Before running this task" notes in Tasks 5 and 6.
- **Type consistency:** `extract_phrase` is introduced in Task 2 and used in Tasks 3 and 4, with the same name and error message.
- **Addition beyond the spec:** `extract_phrase` is a small helper not named in the spec. It keeps the validation rule in one tested place instead of duplicating it in two HTTP layers.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-10-21-azure-phrase-matcher.md`. Please review the plan. It has 7 tasks, and each task depends on the interfaces of the one before it.

Two decisions for you:

- **Git:** Commit steps are skipped until you approve `git init`. Do you want that?
- **Azure deploy (Tasks 5 and 6):** These create billable resources. I will confirm with you before running them.

Execution method, which one do you prefer?

- **Subagent-driven:** a fresh subagent implements each task, and a fresh reviewer checks it before the next starts. Most thorough, but costs more.
- **Native:** I implement every task in this session, then one reviewer checks the whole branch. Cheaper and faster.

I recommend **Native**. The tasks are sequential and small, each one builds directly on the last, and the plan already carries the interfaces, so per-task review adds cost without catching much more.

Does the plan capture what you want, and which approach should we use?
