# DO Deploy Analyzer

AI-powered deployment failure analysis for DigitalOcean App Platform. Automatically detects failed deployments, fetches your codebase, analyzes with GPT-4, and posts actionable fix suggestions directly to GitHub commits.

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/aupadhyay-shark/do-deploy-analyzer/tree/main)

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
  - [High-Level Overview](#high-level-overview)
  - [Component Diagram](#component-diagram)
  - [Data Flow](#data-flow)
  - [Module Breakdown](#module-breakdown)
- [Setup Guide](#setup-guide)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Example Output](#example-output)
- [Function Reference](#function-reference)
- [Deployment](#deployment)
- [Local Development](#local-development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| 🔄 **Automatic Polling** | Polls all DO apps every 60 seconds - no webhook setup required |
| 🔍 **Build Failure Detection** | Detects failed builds from deployment phase and progress steps |
| 💥 **Runtime Crash Detection** | Monitors active deployments for runtime errors and crashes |
| 📦 **Codebase Fetching** | Fetches Dockerfile, requirements.txt, package.json, and source files |
| 🤖 **AI-Powered Analysis** | GPT-4 analyzes both logs AND codebase for accurate root cause |
| 💬 **GitHub Comments** | Posts detailed fix suggestions directly on the failing commit |
| 🔗 **Auto Repo Detection** | Automatically discovers GitHub repo from DO app configuration |
| 📊 **Multiple App Support** | Monitors all apps in your DO account simultaneously |

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DO DEPLOY ANALYZER                                  │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │   POLLING   │───▶│  DETECTION  │───▶│  ANALYSIS   │───▶│   POSTING   │   │
│  │  (60 sec)   │    │  (Failures) │    │   (GPT-4)   │    │  (GitHub)   │   │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘   │
│         │                  │                  │                  │           │
│         ▼                  ▼                  ▼                  ▼           │
│    DO API Call       Check Phase        Fetch Codebase    Post Comment      │
│    List Apps         Check Steps        Fetch Logs        on Commit         │
│    Get Deploys       Check Runtime      Call OpenAI                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Flow

1. **Poll**: Background task queries DigitalOcean API every 60 seconds
2. **List**: Fetches all apps in your DO account
3. **Check**: For each app, checks last 3 deployments for failures
4. **Detect**: Identifies failures from:
   - Deployment phase (ERROR, FAILED, CANCELED)
   - Progress steps (build step failures)
   - Runtime logs (exceptions, crashes in ACTIVE deployments)
5. **Fetch Codebase**: Downloads relevant files from GitHub:
   - `Dockerfile`, `requirements.txt`, `package.json`
   - `.do/app.yaml`, `Procfile`
   - Main source files (`.py`, `.js`, `.ts`)
6. **Fetch Logs**: Gets build/run logs from DO API
7. **Analyze**: Sends codebase + logs to GPT-4 for analysis
8. **Post**: Creates a comment on the failing commit in GitHub

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    EXTERNAL SERVICES                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐                │
│    │  DigitalOcean │      │    GitHub     │      │    OpenAI     │                │
│    │  App Platform │      │     API       │      │     API       │                │
│    └───────┬───────┘      └───────┬───────┘      └───────┬───────┘                │
│            │                      │                      │                         │
│            │ REST API             │ REST API             │ REST API                │
│            │                      │                      │                         │
└────────────┼──────────────────────┼──────────────────────┼─────────────────────────┘
             │                      │                      │
             ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DO DEPLOY ANALYZER (FastAPI)                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           BACKGROUND POLLING TASK                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │   │
│  │  │poll_for_    │─▶│check_all_   │─▶│check_app_   │─▶│check_for_   │        │   │
│  │  │failed_      │  │apps_for_    │  │deployment() │  │runtime_     │        │   │
│  │  │deployments()│  │failures()   │  │             │  │errors()     │        │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
│                                        ▼ (on failure detected)                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           FAILURE PROCESSING PIPELINE                        │   │
│  │                                                                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │   │
│  │  │get_do_app_  │─▶│fetch_       │─▶│fetch_       │─▶│analyze_     │        │   │
│  │  │info()       │  │codebase_    │  │deployment_  │  │deployment_  │        │   │
│  │  │             │  │context()    │  │logs()       │  │failure()    │        │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │   │
│  │                                                              │               │   │
│  │                                                              ▼               │   │
│  │                                                    ┌─────────────┐          │   │
│  │                                                    │post_analysis│          │   │
│  │                                                    │_to_github() │          │   │
│  │                                                    └─────────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                              REST API ENDPOINTS                              │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌───────────────┐              │   │
│  │  │ /health │  │/analyze │  │/register-   │  │/webhook/github│              │   │
│  │  │         │  │         │  │repo         │  │               │              │   │
│  │  └─────────┘  └─────────┘  └─────────────┘  └───────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                              IN-MEMORY STATE                                 │   │
│  │  ┌─────────────────────────┐  ┌─────────────────────────────────┐          │   │
│  │  │ processed_deployments   │  │ repo_app_mappings               │          │   │
│  │  │ Set[str]                │  │ Dict[repo, app_id]              │          │   │
│  │  │ (prevents duplicates)   │  │ (manual repo→app mapping)      │          │   │
│  │  └─────────────────────────┘  └─────────────────────────────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              app.py                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    1. POLLING SYSTEM                             │   │
│  │                                                                  │   │
│  │  poll_for_failed_deployments()   # Infinite loop, runs every    │   │
│  │         │                          60s in background             │   │
│  │         ▼                                                        │   │
│  │  check_all_apps_for_failures()   # GET /v2/apps                 │   │
│  │         │                                                        │   │
│  │         ▼                                                        │   │
│  │  check_app_deployment()          # GET /v2/apps/{id}/deployments│   │
│  │         │                          - Check phase: ERROR/FAILED  │   │
│  │         │                          - Check progress steps       │   │
│  │         │                          - Skip if >10 min old        │   │
│  │         ▼                                                        │   │
│  │  check_for_runtime_errors()      # GET .../logs?type=RUN        │   │
│  │                                    - Pattern match for errors   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    2. CODEBASE FETCHING                          │   │
│  │                                                                  │   │
│  │  fetch_codebase_context()        # Main entry point             │   │
│  │         │                                                        │   │
│  │         ├──▶ fetch_repo_tree()   # GET /repos/{}/git/trees/{}   │   │
│  │         │                          - Recursive tree listing     │   │
│  │         │                                                        │   │
│  │         └──▶ fetch_file_content()# GET /repos/{}/contents/{}    │   │
│  │                                    - Base64 decode content      │   │
│  │                                                                  │   │
│  │  FILES FETCHED:                                                  │   │
│  │  ├── Dockerfile, docker-compose.yml                             │   │
│  │  ├── requirements.txt, package.json, go.mod                     │   │
│  │  ├── .do/app.yaml, Procfile                                     │   │
│  │  ├── *.py, *.js, *.ts (root level)                              │   │
│  │  └── .do/*, deploy/* directories                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    3. FAILURE PROCESSING                         │   │
│  │                                                                  │   │
│  │  process_failed_deployment()                                     │   │
│  │         │                                                        │   │
│  │         ├──▶ get_do_app_info()       # Extract GitHub repo,     │   │
│  │         │                              commit SHA from DO app   │   │
│  │         │                                                        │   │
│  │         ├──▶ fetch_latest_deployment_logs()  # BUILD then RUN   │   │
│  │         │                                                        │   │
│  │         ├──▶ fetch_codebase_context()  # Get source files       │   │
│  │         │                                                        │   │
│  │         ├──▶ analyze_deployment_failure()  # Call GPT-4         │   │
│  │         │                                                        │   │
│  │         └──▶ post_analysis_to_github()  # POST commit comment   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    4. GITHUB AUTHENTICATION                      │   │
│  │                                                                  │   │
│  │  GitHub App Auth Flow:                                           │   │
│  │                                                                  │   │
│  │  generate_jwt_token()            # Create JWT with App ID       │   │
│  │         │                          + Private Key (RS256)        │   │
│  │         ▼                                                        │   │
│  │  find_installation_for_repo()    # Find installation ID for     │   │
│  │         │                          the target repository        │   │
│  │         ▼                                                        │   │
│  │  get_installation_token()        # Exchange JWT for short-lived │   │
│  │                                    installation access token    │   │
│  │                                                                  │   │
│  │  Token Permissions Required:                                     │   │
│  │  ├── Contents: read (for fetching code)                         │   │
│  │  ├── Commit comments: write (for posting analysis)              │   │
│  │  └── Checks: read & write (optional)                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    5. LLM ANALYSIS                               │   │
│  │                                                                  │   │
│  │  analyze_deployment_failure(logs, repo, commit, codebase)       │   │
│  │                                                                  │   │
│  │  PROMPT STRUCTURE:                                               │   │
│  │  ┌────────────────────────────────────────────────────────┐     │   │
│  │  │ Repository: {repo_name}                                 │     │   │
│  │  │ Commit: {commit_sha}                                    │     │   │
│  │  │                                                         │     │   │
│  │  │ CODEBASE FILES:                                         │     │   │
│  │  │ === FILE: Dockerfile ===                                │     │   │
│  │  │ FROM python:3.11...                                     │     │   │
│  │  │                                                         │     │   │
│  │  │ === FILE: requirements.txt ===                          │     │   │
│  │  │ fastapi==0.115...                                       │     │   │
│  │  │                                                         │     │   │
│  │  │ DEPLOYMENT/BUILD LOGS:                                  │     │   │
│  │  │ [last 6000 chars of logs]                               │     │   │
│  │  └────────────────────────────────────────────────────────┘     │   │
│  │                                                                  │   │
│  │  OUTPUT FORMAT:                                                  │   │
│  │  ├── 🔍 Root Cause (with file:line references)                  │   │
│  │  ├── 🛠️ Suggested Fix (copy-paste ready)                        │   │
│  │  ├── 📚 Related Documentation                                   │   │
│  │  └── 💡 Prevention Tips                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    6. DO API INTEGRATION                         │   │
│  │                                                                  │   │
│  │  get_do_app_info()                                               │   │
│  │  ├── GET /v2/apps/{app_id}                                      │   │
│  │  ├── Extract GitHub repo from spec.services[].github.repo       │   │
│  │  └── Extract commit SHA from deployment.cause.commit_sha        │   │
│  │                                                                  │   │
│  │  fetch_latest_deployment_logs()                                  │   │
│  │  ├── GET /v2/apps/{id}/deployments (find failed one)            │   │
│  │  ├── GET /v2/apps/{id} (get component name)                     │   │
│  │  ├── GET .../logs?type=BUILD (try build logs first)             │   │
│  │  ├── GET .../logs?type=RUN (fallback to run logs)               │   │
│  │  └── Fetch actual log content from historic_urls                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DETAILED DATA FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

1. POLLING PHASE
   ──────────────
   
   App Startup
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ asyncio.create_task(                    │
   │   poll_for_failed_deployments()         │
   │ )                                        │
   └─────────────────────────────────────────┘
        │
        ▼ (every 60 seconds)
   ┌─────────────────────────────────────────┐
   │ GET https://api.digitalocean.com/v2/apps│
   │ Headers: Authorization: Bearer {TOKEN}  │
   └─────────────────────────────────────────┘
        │
        ▼ (response)
   {
     "apps": [
       {"id": "abc123", "spec": {"name": "my-app"}},
       {"id": "def456", "spec": {"name": "other-app"}}
     ]
   }
        │
        ▼ (for each app)
   ┌─────────────────────────────────────────┐
   │ GET /v2/apps/{app_id}/deployments       │
   │ Params: per_page=3                      │
   └─────────────────────────────────────────┘
        │
        ▼ (check each deployment)
   ┌─────────────────────────────────────────┐
   │ Is deployment_id in processed_set?      │──▶ YES ──▶ Skip
   │                                         │
   │ Is deployment older than 10 minutes?    │──▶ YES ──▶ Add to set, Skip
   │                                         │
   │ Is phase in [ERROR, FAILED, CANCELED]?  │──▶ YES ──▶ Process
   │                                         │
   │ Any step.status in [ERROR, FAILED]?     │──▶ YES ──▶ Process
   │                                         │
   │ If ACTIVE, check runtime errors         │──▶ YES ──▶ Process
   └─────────────────────────────────────────┘


2. CODEBASE FETCHING PHASE
   ────────────────────────
   
   ┌─────────────────────────────────────────┐
   │ find_installation_for_repo(owner, repo) │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ GET /app/installations                   │
   │ Headers: Authorization: Bearer {JWT}    │
   └─────────────────────────────────────────┘
        │
        ▼ (find matching installation)
   ┌─────────────────────────────────────────┐
   │ POST /app/installations/{id}/access_    │
   │      tokens                              │
   │ Returns: Installation Token (1 hour)    │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ GET /repos/{owner}/{repo}/git/trees/    │
   │     {commit_sha}?recursive=1            │
   │ Headers: Authorization: Bearer {TOKEN}  │
   └─────────────────────────────────────────┘
        │
        ▼ (filter relevant files)
   [
     "Dockerfile",
     "requirements.txt",
     ".do/app.yaml",
     "app.py"
   ]
        │
        ▼ (for each file, max 15)
   ┌─────────────────────────────────────────┐
   │ GET /repos/{owner}/{repo}/contents/{path}│
   │ Response: {"content": "BASE64...",      │
   │            "encoding": "base64"}        │
   └─────────────────────────────────────────┘
        │
        ▼ (decode and format)
   """
   === FILE: Dockerfile ===
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   ...

   === FILE: requirements.txt ===
   fastapi==0.115.12
   uvicorn==0.34.0
   ...
   """


3. LOG FETCHING PHASE
   ───────────────────
   
   ┌─────────────────────────────────────────┐
   │ GET /v2/apps/{app_id}/deployments       │
   │ Find deployment with phase=ERROR/FAILED │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ GET /v2/apps/{app_id}                   │
   │ Extract: services[0].name (component)   │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ GET /v2/apps/{app_id}/deployments/      │
   │     {deployment_id}/components/         │
   │     {component_name}/logs               │
   │ Params: type=BUILD, follow=false        │
   └─────────────────────────────────────────┘
        │
        ▼ (response)
   {
     "historic_urls": [
       "https://appbuild-logs.nyc3.digitaloceanspaces.com/..."
     ]
   }
        │
        ▼
   ┌─────────────────────────────────────────┐
   │ GET {historic_urls[0]}                  │
   │ Returns: Plain text build logs          │
   └─────────────────────────────────────────┘


4. ANALYSIS PHASE
   ───────────────
   
   ┌─────────────────────────────────────────┐
   │ POST https://api.openai.com/v1/chat/    │
   │      completions                         │
   │                                          │
   │ {                                        │
   │   "model": "gpt-4o-mini",               │
   │   "messages": [                          │
   │     {"role": "system", "content":       │
   │      "You are a DevOps expert..."},     │
   │     {"role": "user", "content":         │
   │      "Repository: ...\n                 │
   │       CODEBASE FILES:\n...\n            │
   │       DEPLOYMENT LOGS:\n..."}           │
   │   ],                                     │
   │   "max_tokens": 2000,                   │
   │   "temperature": 0.3                    │
   │ }                                        │
   └─────────────────────────────────────────┘
        │
        ▼ (response)
   """
   ## 🔍 Root Cause
   The build failed because `numpy` in requirements.txt
   requires compilation but the Dockerfile is missing
   build-essential.

   ## 🛠️ Suggested Fix
   Add this line to your Dockerfile before pip install:
   ```dockerfile
   RUN apt-get update && apt-get install -y build-essential
   ```

   ## 📚 Related Documentation
   - https://docs.digitalocean.com/...

   ## 💡 Prevention Tips
   - Use slim-buster instead of alpine for Python
   """


5. POSTING PHASE
   ──────────────
   
   ┌─────────────────────────────────────────┐
   │ POST /repos/{owner}/{repo}/commits/     │
   │      {commit_sha}/comments              │
   │                                          │
   │ Headers:                                 │
   │   Authorization: Bearer {TOKEN}         │
   │   Accept: application/vnd.github+json   │
   │                                          │
   │ Body:                                    │
   │ {                                        │
   │   "body": "## 🚨 Deployment Failed...\n │
   │            **App:** `my-app`\n          │
   │            **Commit:** `abc1234`\n      │
   │            ---\n                        │
   │            [analysis]\n                 │
   │            ---\n                        │
   │            <details>...</details>"      │
   │ }                                        │
   └─────────────────────────────────────────┘
        │
        ▼
   Comment appears on GitHub commit! ✅
```

### Module Breakdown

```
app.py (752 lines)
│
├── CONFIGURATION (Lines 1-35)
│   ├── Environment variables
│   ├── DO_API_BASE, DIGITALOCEAN_TOKEN
│   ├── GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY
│   ├── OPENAI_API_KEY
│   └── POLL_INTERVAL_SECONDS, ENABLE_POLLING
│
├── STATE (Lines 34-35)
│   ├── processed_deployments: Set[str]  # Prevent duplicate processing
│   └── repo_app_mappings: Dict          # Manual repo→app_id mapping
│
├── POLLING SYSTEM (Lines 38-163)
│   ├── poll_for_failed_deployments()    # Background loop
│   ├── check_all_apps_for_failures()    # List all apps
│   ├── check_app_deployment()           # Check single app
│   └── check_for_runtime_errors()       # Detect crashes
│
├── FAILURE PROCESSING (Lines 166-202)
│   └── process_failed_deployment()      # Main orchestrator
│
├── APP LIFECYCLE (Lines 205-222)
│   ├── lifespan()                       # Start background task
│   └── FastAPI app initialization
│
├── GITHUB AUTHENTICATION (Lines 225-308)
│   ├── generate_jwt_token()             # Create JWT
│   ├── get_installation_token()         # Get access token
│   ├── find_installation_for_repo()     # Find installation ID
│   └── get_latest_commit_from_github()  # Get HEAD commit
│
├── CODEBASE FETCHING (Lines 311-455)
│   ├── BUILD_RELATED_FILES              # List of files to fetch
│   ├── fetch_file_content()             # Fetch single file
│   ├── fetch_repo_tree()                # List all files
│   └── fetch_codebase_context()         # Main entry point
│
├── LLM ANALYSIS (Lines 458-519)
│   └── analyze_deployment_failure()     # Call GPT-4
│
├── GITHUB POSTING (Lines 522-576)
│   └── post_analysis_to_github()        # Post commit comment
│
├── DO API INTEGRATION (Lines 579-676)
│   ├── get_do_app_info()                # Get app metadata
│   └── fetch_latest_deployment_logs()   # Get build/run logs
│
└── API ENDPOINTS (Lines 679-750)
    ├── GET  /health                     # Health check
    ├── GET  /                           # Root
    ├── POST /webhook/github             # Webhook receiver
    ├── POST /analyze                    # Manual analysis
    └── POST /register-repo              # Map repo to app
```

---

## Setup Guide

### 1. Create GitHub App

1. Go to [GitHub Developer Settings](https://github.com/settings/apps/new)

2. Fill in the basic information:
   - **Name**: `DO Deploy Analyzer`
   - **Homepage URL**: Your app URL
   - **Webhook**: Uncheck "Active" (we use polling instead)

3. Set permissions:
   ```
   Repository permissions:
   ├── Contents: Read-only        (to fetch codebase)
   ├── Commit comments: Read & write (to post analysis)
   └── Metadata: Read-only        (required)
   ```

4. After creation, note down:
   - **App ID**: Found at the top of the settings page
   - **Private Key**: Generate and download (click "Generate a private key")

5. Convert private key to single line (for env var):
   ```bash
   awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' ~/Downloads/your-key.pem
   ```

### 2. Deploy to DigitalOcean

**Option A: One-Click Deploy**

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/aupadhyay-shark/do-deploy-analyzer/tree/main)

**Option B: Manual Deploy**

1. Fork/clone this repo
2. Create a new app in DO App Platform
3. Connect your GitHub repo
4. Set environment variables (see below)

### 3. Install GitHub App

1. Go to your GitHub App settings page
2. Click "Install App" in left sidebar
3. Select the repositories you want to monitor
4. The app will automatically start analyzing failures!

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DIGITALOCEAN_TOKEN` | **Yes** | - | DO API token (needs read access to apps) |
| `GITHUB_APP_ID` | **Yes** | - | Your GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | **Yes** | - | PEM key with `\n` for newlines |
| `OPENAI_API_KEY` | **Yes** | - | OpenAI API key for GPT-4 |
| `GITHUB_WEBHOOK_SECRET` | No | - | Webhook secret (optional) |
| `POLL_INTERVAL_SECONDS` | No | `60` | How often to poll DO (seconds) |
| `ENABLE_POLLING` | No | `true` | Enable/disable background polling |

### Example `.env`

```bash
# DigitalOcean
DIGITALOCEAN_TOKEN=dop_v1_your_token_here

# GitHub App
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n"

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Optional
POLL_INTERVAL_SECONDS=60
ENABLE_POLLING=true
```

---

## API Reference

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-31T12:00:00.000000",
  "github_configured": true,
  "openai_configured": true,
  "do_configured": true
}
```

### `GET /`

Root endpoint.

**Response:**
```json
{
  "name": "DO Deploy Analyzer",
  "docs": "/docs"
}
```

### `POST /analyze`

Manually trigger analysis for a repository.

**Request Body:**
```json
{
  "repo": "owner/repo-name",
  "logs": "optional raw logs",
  "do_app_id": "optional DO app ID to fetch logs from"
}
```

**Response:**
```json
{
  "status": "analyzed",
  "analysis": "## 🔍 Root Cause\n..."
}
```

### `POST /register-repo`

Map a GitHub repository to a DO app ID (for apps that can't be auto-detected).

**Query Parameters:**
- `repo`: GitHub repository (e.g., `owner/repo`)
- `do_app_id`: DigitalOcean app ID

**Response:**
```json
{
  "status": "registered",
  "repo": "owner/repo",
  "do_app_id": "abc123"
}
```

### `POST /webhook/github`

Receives GitHub webhooks (optional - polling is the primary method).

**Headers:**
- `X-GitHub-Event`: Event type
- `X-Hub-Signature-256`: HMAC signature

---

## Example Output

When a deployment fails, you'll see a comment like this on the commit:

```markdown
## 🚨 Deployment Failed - AI Analysis

**App:** `seal-app`
**Commit:** `ba5d7beb`
**Time:** 2026-01-31 11:03:48 UTC

---

## 🔍 Root Cause
The build failed because `numpy==2.0.0` in `requirements.txt` (line 15)
requires compilation, but the Dockerfile is using `python:3.11-alpine`
which doesn't include the necessary build tools.

## 🛠️ Suggested Fix

**Option 1:** Change base image in `Dockerfile` (line 1):
```dockerfile
# Before
FROM python:3.11-alpine

# After
FROM python:3.11-slim
```

**Option 2:** Add build dependencies:
```dockerfile
RUN apk add --no-cache gcc musl-dev python3-dev
```

## 📚 Related Documentation
- [DigitalOcean: Python Buildpacks](https://docs.digitalocean.com/products/app-platform/languages-frameworks/python/)
- [NumPy Installation Guide](https://numpy.org/install/)

## 💡 Prevention Tips
- Use `python:3.11-slim` instead of `alpine` for Python apps with native dependencies
- Pin package versions: `numpy==1.26.4` (pure wheel available)
- Test Docker builds locally before pushing

---

<details>
<summary>Log Snippet</summary>

```
Building wheels for collected packages: numpy
  Building wheel for numpy (pyproject.toml): started
  error: subprocess-exited-with-error
  × Building wheel for numpy (pyproject.toml) did not run successfully.
```

</details>

---
*Powered by DO Deploy Analyzer*
```

---

## Function Reference

### Polling Functions

| Function | Description |
|----------|-------------|
| `poll_for_failed_deployments()` | Background task that runs every 60s |
| `check_all_apps_for_failures()` | Lists all DO apps and checks each |
| `check_app_deployment(app_id, app_name)` | Checks last 3 deployments for failures |
| `check_for_runtime_errors(app_id, deployment_id, app_name)` | Scans runtime logs for error patterns |

### GitHub Functions

| Function | Description |
|----------|-------------|
| `generate_jwt_token()` | Creates JWT for GitHub App auth |
| `get_installation_token(installation_id)` | Gets short-lived access token |
| `find_installation_for_repo(owner, repo)` | Finds GitHub App installation ID |
| `get_latest_commit_from_github(repo)` | Gets HEAD commit SHA |
| `post_analysis_to_github(repo, commit, analysis, app_name, logs)` | Posts comment |

### Codebase Functions

| Function | Description |
|----------|-------------|
| `fetch_codebase_context(owner, repo, commit_sha)` | Fetches all relevant files |
| `fetch_repo_tree(client, owner, repo, token, sha)` | Gets recursive file listing |
| `fetch_file_content(client, owner, repo, path, token)` | Fetches single file content |

### Analysis Functions

| Function | Description |
|----------|-------------|
| `process_failed_deployment(app_id, app_name, deployment)` | Main orchestrator |
| `analyze_deployment_failure(logs, repo, commit, codebase)` | Calls GPT-4 |
| `fetch_latest_deployment_logs(app_id)` | Gets build/run logs from DO |
| `get_do_app_info(app_id)` | Gets GitHub repo and commit from DO app |

---

## Deployment

### DigitalOcean App Platform

The `.do/app.yaml` is included for easy deployment:

```yaml
name: do-deploy-analyzer
region: nyc
services:
  - name: web
    github:
      repo: aupadhyay-shark/do-deploy-analyzer
      branch: main
    http_port: 8000
    instance_size_slug: apps-s-1vcpu-0.5gb
    instance_count: 1
    dockerfile_path: Dockerfile
```

### Docker

```bash
docker build -t do-deploy-analyzer .
docker run -p 8000:8000 \
  -e DIGITALOCEAN_TOKEN=... \
  -e GITHUB_APP_ID=... \
  -e GITHUB_APP_PRIVATE_KEY=... \
  -e OPENAI_API_KEY=... \
  do-deploy-analyzer
```

---

## Local Development

```bash
# Clone
git clone https://github.com/aupadhyay-shark/do-deploy-analyzer
cd do-deploy-analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
uvicorn app:app --reload --port 8000

# Access docs
open http://localhost:8000/docs
```

---

## Troubleshooting

### No comments appearing on commits

1. **Check GitHub App is installed** on the repository
2. **Verify permissions**: Contents (read), Commit comments (write)
3. **Check logs** for authentication errors

### Polling not detecting failures

1. **Check DIGITALOCEAN_TOKEN** has read access
2. **Verify ENABLE_POLLING** is `true`
3. Failures older than 10 minutes are skipped

### Analysis is generic (not referencing code)

1. **Check GitHub App installation** on the repo
2. **Verify Contents permission** is granted
3. Check logs for "Could not authenticate with GitHub"

### OpenAI errors

1. **Verify OPENAI_API_KEY** is valid
2. Check you have API credits
3. Check rate limits

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## Support

- **Issues**: [GitHub Issues](https://github.com/aupadhyay-shark/do-deploy-analyzer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aupadhyay-shark/do-deploy-analyzer/discussions)
