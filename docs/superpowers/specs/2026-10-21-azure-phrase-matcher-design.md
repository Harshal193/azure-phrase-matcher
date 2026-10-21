# Phrase Matcher on Azure Functions — Design

**Date:** 2026-10-21
**Goal:** Learn to run Python on Azure Functions (and compare with Azure App Service) by building a small service that returns the closest match to a user phrase from a fixed list.

## 1. Scope

**In scope**

- A Python HTTP-triggered Azure Function (Python v2 programming model) that matches a phrase.
- The same matching logic served by a small Flask app for App Service.
- Local setup, run, and test steps. Deployment and endpoint testing steps for both Azure services.
- A comparison of the two approaches.

**Out of scope**

- AI, embeddings, or Azure OpenAI.
- Databases, user accounts, or authentication (the endpoint is public for learning).
- CI/CD pipelines, infrastructure as code, custom domains, monitoring setup.

## 2. Assumptions

- Developer machine: Windows, Python 3.11 (already installed), PowerShell.
- Azure Functions Core Tools v4 and Azure CLI will be installed during implementation.
- The project folder is not a git repository today. The spec is therefore saved but not committed. Committing requires `git init`, which the user has not yet approved.

## 3. Architecture

Two deployable apps share one pure-Python module:

```
Azure_Function_Deploy/
├── docs/superpowers/specs/2026-10-21-azure-phrase-matcher-design.md
├── functions/                     # Azure Functions app (Python v2 model)
│   ├── function_app.py            # HTTP trigger: POST /api/match
│   ├── matcher.py                 # Pure logic, no Azure imports
│   ├── phrases.json               # 15 predefined phrases
│   ├── requirements.txt           # azure-functions
│   ├── host.json
│   ├── local.settings.json        # Local only; never deployed
│   └── .funcignore
├── app_service/                   # Flask app for the App Service comparison
│   ├── app.py                     # POST /match
│   ├── matcher.py                 # Copy of functions/matcher.py (see §8)
│   ├── phrases.json               # Copy of functions/phrases.json
│   └── requirements.txt           # flask, gunicorn
├── tests/
│   ├── conftest.py                # Adds functions/ to sys.path
│   └── test_matcher.py            # pytest unit tests
├── requirements-dev.txt           # pytest
└── README.md                      # Setup, run, test, deploy, compare
```

Why the split: `matcher.py` contains all business logic. It has no Azure imports, so it can be tested with plain pytest and reused unchanged. The two HTTP layers are thin wrappers.

## 4. Components

### 4.1 `matcher.py`

- `load_phrases(path) -> list[str]`: reads a JSON array of strings. Raises `ValueError` if the content is not a non-empty list of strings.
- `normalize(text) -> str`: lowercases, strips leading/trailing whitespace, collapses internal whitespace to single spaces.
- `find_closest(query, phrases) -> tuple[str, float]`: returns the best phrase and its similarity score in `[0.0, 1.0]`, using `difflib.SequenceMatcher(None, normalize(query), normalize(phrase)).ratio()`, rounded to 2 decimals. Ties go to the earlier phrase in the list. The query must already be validated as non-empty (see §5).

No minimum-score threshold in v1. The best match is always returned with its score, so the user can see confidence. A threshold is a possible later addition.

### 4.2 `function_app.py` (Azure Functions)

- Loads `phrases.json` once at module import (cold start), using a path relative to `__file__`.
- One route: `@app.route(route="match", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)`. The public URL is `/api/match`.
- Parses the JSON body, validates it, calls `find_closest`, returns JSON.

### 4.3 `app.py` (App Service)

- Same behavior and response format as the Function, at `POST /match`.
- Loads `phrases.json` once at startup.
- Served by gunicorn on Azure.

## 5. API Contract

**Request:** `POST /api/match` (Functions) or `POST /match` (App Service)

```json
{ "phrase": "helo wrld" }
```

**Success (200):**

```json
{ "match": "hello world", "score": 0.91 }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| Body is not valid JSON | 400 | `{"error": "Request body must be valid JSON."}` |
| `phrase` missing, not a string, or blank after trim | 400 | `{"error": "'phrase' must be a non-empty string."}` |
| Unexpected exception | 500 | `{"error": "Internal server error."}` (details go to the log, not the response) |

Wrong HTTP method is handled by the framework (405 for App Service; Functions returns 405 for a route that does not allow the method).

## 6. Data Flow

1. Client sends `POST` with JSON `{"phrase": ...}`.
2. HTTP layer parses and validates the body.
3. HTTP layer calls `find_closest(phrase, PHRASES)`.
4. HTTP layer returns `{"match", "score"}` with status 200.

Phrases are read from `phrases.json` at startup and held in memory. No per-request file I/O.

## 7. Error Handling

- Validation errors are handled in the HTTP layer and return 400 before the matcher runs.
- `load_phrases` failures stop the app at startup with a clear message. This surfaces configuration errors early instead of at the first request.
- Unexpected errors are logged with the stack trace and return a generic 500.

## 8. Duplication Decision

`matcher.py` and `phrases.json` are copied into `app_service/`, not shared through a package or symlink. Reason: each deploy target is self-contained. Azure deploys a folder, and cross-folder imports complicate the deploy step for a beginner. The duplication is intentional and documented in the README. If the copies drift, the tests in `tests/` run against `functions/matcher.py`, and the README explains how to re-copy.

## 9. Testing

**Unit tests (pytest, no Azure needed):**

- `normalize`: case, whitespace, empty string.
- `find_closest`: exact match returns score 1.0; near-miss picks the right phrase; the same query always returns the same result; tie goes to the earlier phrase.
- `load_phrases`: valid file; empty list raises; non-string item raises.

**HTTP tests (manual, per environment):**

- Local Functions: `func start`, then `curl` the valid and invalid cases from §5 against `http://localhost:7071/api/match`.
- Local App Service: `flask`/`gunicorn` run, then the same cases against `http://localhost:8000/match`.
- Deployed: the same cases against each Azure URL.

A single `curl` checklist in the README covers all three environments.

## 10. Deployment

- **Azure Functions:** create a resource group, storage account, and Function App (Linux, Python 3.11, Consumption plan). Deploy with `func azure functionapp publish <app-name>`.
- **App Service:** create a Linux App Service plan (B1 or F1) and a web app with Python 3.11. Deploy with `az webapp up`. Startup command: `gunicorn --bind 0.0.0.0:8000 app:app`.

Both use the same region and resource group names so the comparison is fair.

## 11. Comparison (for the README)

| Aspect | Azure Functions (Consumption) | App Service (Linux) |
|---|---|---|
| Model | Event-driven; code is a function | Always-on web app |
| Scaling | Automatic, scales to zero | Manual or rule-based on the plan |
| Cost at low traffic | Near zero (free grant) | Fixed monthly plan cost |
| Cold start | Possible after idle | None on paid tiers |
| Deploy | `func ... publish` | `az webapp up` |
| Best for | Small, spiky, event-driven work | Full web apps, always-on APIs |

The comparison will be checked against the official docs during implementation before it goes into the README.

## 12. Open Points for Review

- Confirm the Consumption plan for Functions and B1 for App Service are acceptable on your subscription.
- Confirm the public, unauthenticated endpoint is acceptable for this learning project.
