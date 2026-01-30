# DO Deploy Analyzer

AI-powered deployment failure analysis for DigitalOcean App Platform. Automatically detects failed deployments, analyzes logs with GPT-4, and posts suggestions directly to GitHub.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     DO Deploy Analyzer                          │
│                                                                 │
│   Poll DO API ──▶ Detect Failure ──▶ Analyze Logs ──▶ Post to  │
│   (every 60s)                        (GPT-4)         GitHub    │
└─────────────────────────────────────────────────────────────────┘
```

1. **Polls** all your DigitalOcean apps every 60 seconds
2. **Detects** build failures and runtime crashes
3. **Fetches** deployment logs from DO API
4. **Analyzes** with GPT-4 to identify root cause and suggest fixes
5. **Posts** analysis as a comment on the failing commit in GitHub

## Features

- Automatic polling (no webhook setup required)
- Detects both build failures and runtime crashes
- AI-powered root cause analysis
- Posts directly to GitHub commits
- Works with any DO App Platform app

## Quick Start

### 1. Create GitHub App

1. Go to [GitHub Developer Settings](https://github.com/settings/apps/new)
2. Create app with permissions:
   - **Checks**: Read & write
   - **Commit statuses**: Read & write
   - **Contents**: Read-only
3. Generate and download private key
4. Note your App ID

### 2. Deploy to DigitalOcean

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/aupadhyay-shark/do-deploy-analyzer/tree/main)

Or manually:
1. Create app from this repo
2. Set environment variables (see below)

### 3. Set Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DIGITALOCEAN_TOKEN` | Yes | DO API token (for fetching logs) |
| `GITHUB_APP_ID` | Yes | Your GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | Yes | GitHub App private key (PEM) |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `GITHUB_WEBHOOK_SECRET` | No | Webhook secret (if using webhooks) |
| `POLL_INTERVAL_SECONDS` | No | Polling interval (default: 60) |
| `ENABLE_POLLING` | No | Enable/disable polling (default: true) |

### 4. Install GitHub App

1. Go to your GitHub App settings
2. Install on repositories you want to monitor
3. That's it! The analyzer will automatically detect failures

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/analyze` | POST | Manually analyze logs |
| `/register-repo` | POST | Map repo to DO app ID |
| `/webhook/github` | POST | GitHub webhook receiver |

## Example Output

When a deployment fails, you'll see a comment like this on the commit:

```markdown
## 🚨 Deployment Failed - AI Analysis

**App:** `my-app`
**Commit:** `abc12345`

---

## Root Cause
The deployment failed because `express` is not imported before use.

## Suggested Fix
Add this import at the top of your file:
const express = require('express');
const app = express();

## Prevention Tips
- Use a linter to catch undefined variables
- Add pre-commit hooks to validate code
```

## Local Development

```bash
# Clone
git clone https://github.com/aupadhyay-shark/do-deploy-analyzer
cd do-deploy-analyzer

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
uvicorn app:app --reload
```

## Architecture

```
app.py
├── Polling System
│   ├── poll_for_failed_deployments()  # Background task
│   ├── check_all_apps_for_failures()  # Check all apps
│   ├── check_app_deployment()         # Check single app
│   └── check_for_runtime_errors()     # Detect crashes
│
├── Analysis
│   ├── process_failed_deployment()    # Main handler
│   ├── analyze_deployment_failure()   # LLM analysis
│   └── fetch_latest_deployment_logs() # Get logs
│
├── GitHub Integration
│   ├── find_installation_for_repo()   # Find app installation
│   ├── get_installation_token()       # Auth token
│   └── post_analysis_to_github()      # Post comment
│
└── DO Integration
    └── get_do_app_info()              # Get app details
```

## License

MIT
