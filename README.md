# Phrase Matcher on Azure Functions and App Service

A small Python service. You send a phrase, it returns the closest of 15 predefined phrases and a similarity score.

This project is for learning. It runs the same logic in two places:

- **Azure Functions** (`functions/`): an HTTP-triggered function, `POST /api/match`
- **App Service** (`app_service/`): a Flask app, `POST /match`

Both run on Windows with PowerShell. Commands assume you are in the project root unless a step says otherwise.

## Project layout

```
Azure_Function_Deploy/
├── functions/                  # Azure Functions app
│   ├── function_app.py        # HTTP trigger
│   ├── matcher.py             # Matching logic (no Azure imports)
│   ├── phrases.json           # 15 predefined phrases
│   ├── host.json
│   ├── local.settings.json    # Local only, never deployed (create it, see step 2)
│   ├── requirements.txt
│   └── .funcignore
├── app_service/                # Flask app
│   ├── app.py
│   ├── matcher.py             # Copy of functions/matcher.py
│   ├── phrases.json           # Copy of functions/phrases.json
│   └── requirements.txt
├── tests/
│   ├── conftest.py
│   └── test_matcher.py
├── docs/superpowers/           # Spec and implementation plan
├── requirements-dev.txt
└── README.md
```

`matcher.py` and `phrases.json` are copied into `app_service/` on purpose. Each folder is deployed on its own, so each needs its own copy. If you change one, copy it to the other.

---

## Part 1: Local setup

### 1. Create the virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install -r functions/requirements.txt
```

If activation is blocked, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Create the local settings file

`functions/local.settings.json` is not in git. Create it with this content:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "",
    "FUNCTIONS_WORKER_RUNTIME": "python"
  }
}
```

### 3. Install the tools (one time)

```powershell
winget install Microsoft.Azure.FunctionsCoreTools
winget install Microsoft.AzureCLI
```

Open a new terminal afterwards, then check:

```powershell
func --version      # expect 4.x
az --version        # expect a version number
```

---

## Part 2: Run and test locally

### 4. Run the unit tests (no Azure needed)

```powershell
pytest -v
```

Expected: `20 passed`.

### 5. Run the Azure Functions app

Open a terminal in `functions/`, activate the venv, and start the host:

```powershell
cd functions
..\.venv\Scripts\Activate.ps1
func start
```

Expected: the output lists `match: [POST] http://localhost:7071/api/match`.

Leave this window running. In a second terminal, from the project root, define a small helper and call it. PowerShell mangles double quotes passed straight to `curl.exe`, so the helper writes the JSON body to a file first:

```powershell
function Invoke-Match($Url, $Body) {
    $file = Join-Path $env:TEMP "match-body.json"
    [IO.File]::WriteAllText($file, $Body, (New-Object Text.UTF8Encoding($false)))
    curl.exe -s -w "  [%{http_code}]`n" -X POST $Url -H "Content-Type: application/json" --data-binary "@$file"
}

Invoke-Match "http://localhost:7071/api/match" '{"phrase": "helo wrld"}'
```

Expected: `{"match": "hello world", "score": 0.9}` (the score may differ slightly).

### 6. Run the App Service app locally

In a third terminal, from `app_service/`:

```powershell
cd app_service
..\.venv\Scripts\Activate.ps1
python -m flask --app app run --port 8000
```

Expected: `Running on http://127.0.0.1:8000`. Gunicorn is only used on Azure, so it doesn't run on Windows.

### 7. Check both endpoints

These checks work for either local URL. Replace the URL:

| Local URL | Azure Functions | App Service |
|---|---|---|
| Local | `http://localhost:7071/api/match` | `http://localhost:8000/match` |
| Azure | `https://<FUNC_APP>.azurewebsites.net/api/match` | `https://<WEB_APP>.azurewebsites.net/match` |

Use the `Invoke-Match` helper from step 5 (define it again if you opened a new terminal). Set `$URL` to the URL from the table:

```powershell
$URL = "http://localhost:7071/api/match"

# Success (expect 200)
Invoke-Match $URL '{"phrase": "helo wrld"}'

# Blank phrase (expect 400)
Invoke-Match $URL '{"phrase": "   "}'

# Number instead of text (expect 400)
Invoke-Match $URL '{"phrase": 5}'

# Malformed JSON (expect 400)
Invoke-Match $URL '{"phrase": "hi"'
```

Expected responses:

| Case | Status | Body |
|---|---|---|
| Valid phrase | 200 | `{"match": "...", "score": ...}` |
| Blank or number | 400 | `{"error": "'phrase' must be a non-empty string."}` |
| Malformed JSON | 400 | `{"error": "Request body must be valid JSON."}` |

Stop the local servers with `Ctrl+C` when you are done.

---

## Part 3: Deploy to Azure Functions

Deployment creates billable resources. Delete them when you finish (see the cleanup section).

### 8. Set variables

Choose names that are unique. Storage names use lowercase letters and digits only, 3–24 characters.

```powershell
$RG = "rg-phrase-matcher"
$LOC = "eastus"
$STORAGE = "stphrasematcher12345"        # change the digits
$FUNC_APP = "func-phrase-matcher-12345"  # change the digits
```

### 9. Sign in

```powershell
az login
```

Confirm the right subscription is selected:

```powershell
az account show --query name -o tsv
```

### 10. Create the resources

```powershell
az group create -n $RG -l $LOC
az storage account create -n $STORAGE -g $RG -l $LOC --sku Standard_LRS
az functionapp create -g $RG -n $FUNC_APP --storage-account $STORAGE --consumption-plan-location $LOC --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux
```

Each command should finish with `"provisioningState": "Succeeded"` or `"state": "Running"`.

### 11. Publish the code

Publish from the `functions/` folder:

```powershell
cd functions
func azure functionapp publish $FUNC_APP --python
cd ..
```

Expected: the output ends with `Deployment successful` and shows the URL `https://<FUNC_APP>.azurewebsites.net/api/match`.

### 12. Test the deployed function

```powershell
$URL = "https://$FUNC_APP.azurewebsites.net/api/match"
Invoke-Match $URL '{"phrase": "helo wrld"}'
```

The first call can be slow because of a cold start. Repeat the four checks from step 7 against `$URL`.

If a call fails, read the live logs while you repeat it:

```powershell
func azure functionapp logstream $FUNC_APP
```

---

## Part 4: Deploy to App Service

App Service runs the Flask app as a web app. It's billed while the plan exists, so delete it when you finish.

### 13. Set variables

```powershell
$WEB_APP = "app-phrase-matcher-12345"   # globally unique, change the digits
$PLAN = "plan-phrase-matcher"
```

### 14. Create the plan and web app

```powershell
az appservice plan create -g $RG -n $PLAN --is-linux --sku B1
az webapp create -g $RG -p $PLAN -n $WEB_APP --runtime "PYTHON:3.11"
```

### 15. Configure the startup command and build on deploy

```powershell
az webapp config set -g $RG -n $WEB_APP --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 app:app"
az webapp config appsettings set -g $RG -n $WEB_APP --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

`SCM_DO_BUILD_DURING_DEPLOYMENT=true` makes Azure install `requirements.txt` when you deploy. Without it the app won't start.

### 16. Package and deploy

Run this from the project root. It creates a ZIP with the app files at the top level, which is the layout App Service expects:

```powershell
Compress-Archive -Path app_service\* -DestinationPath app_service.zip -Force
az webapp deploy -g $RG -n $WEB_APP --type zip --src-path app_service.zip
```

The deploy command finishes quickly, but the install runs on Azure and can take a minute or two. Watch it with:

```powershell
az webapp log tail -g $RG -n $WEB_APP
```

### 17. Test the deployed app

```powershell
$URL = "https://$WEB_APP.azurewebsites.net/match"
Invoke-Match $URL '{"phrase": "helo wrld"}'
```

Repeat the four checks from step 7 against `$URL`. The responses should match the Azure Functions ones.

---

## Part 5: Compare the two approaches

| Aspect | Azure Functions (Consumption) | App Service (Linux, B1) |
|---|---|---|
| Model | Event-driven; you deploy a function | Always-on web app |
| Scaling | Automatic, scales to zero when idle | Manual or rule-based on the plan |
| Cost at low traffic | Pay per execution, with a free grant | Fixed monthly cost for the plan |
| Cold start | Expected after idle periods | None; the app keeps running |
| Deploy | `func azure functionapp publish` | `az webapp deploy --type zip` |
| Config | `local.settings.json` locally, app settings in Azure | Startup command and app settings |
| Best for | Small, spiky, event-driven work | Full web apps and always-on APIs |

**Plan note:** this guide uses the **Consumption** plan, which Microsoft lists as legacy. Cold starts are expected on it. The current option for new apps is the **Flex Consumption** plan, which has always-ready instances to avoid cold starts. Flex is not used here, so this guide stays with the plan from the design. Switching is a separate step.

---

## Cleanup

Everything created here is in one resource group. Deleting it removes both apps and their plans:

```powershell
az group delete -n $RG --yes --no-wait
```

Check cost and status afterwards with `az group list -o table`.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `func` not found | Open a new terminal after `winget install`. |
| `az` not found | Same as above. |
| Activation blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Port 7071 or 8000 in use | Stop the other process, or change the port. |
| Azure Functions returns 500 after deploy | Run `func azure functionapp logstream $FUNC_APP` and repeat the call. |
| App Service shows the default page | The deploy didn't include `app.py` at the ZIP root. Re-run step 16. |
| App Service returns 500 at startup | `SCM_DO_BUILD_DURING_DEPLOYMENT` is missing or the install failed. Check `az webapp log tail`. |
| Storage or app name already taken | Change the digits in the variables and run the create commands again. |
