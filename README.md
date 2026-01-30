# DO Deploy Analyzer

A GitHub Marketplace App that automatically analyzes DigitalOcean App Platform deployment failures and provides AI-powered suggestions directly in your repository.

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  User pushes    │────▶│  DO deploys     │────▶│  GitHub sends   │
│  code to GitHub │     │  (fails)        │     │  webhook        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Comment on     │◀────│  LLM analyzes   │◀────│  App receives   │
│  commit/PR      │     │  the failure    │     │  event          │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Features

- **Automatic Detection** - Listens to `deployment_status` events from GitHub
- **AI Analysis** - Uses GPT-4 to analyze failure logs and suggest fixes
- **GitHub Integration** - Posts analysis as commit comments and check runs
- **Webhook Security** - Verifies GitHub webhook signatures
- **Configuration API** - Per-installation settings

## Quick Start

### 1. Create a GitHub App

1. Go to **GitHub Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**

2. Configure:
   | Field | Value |
   |-------|-------|
   | Name | `DO Deploy Analyzer` |
   | Homepage URL | `https://your-app.ondigitalocean.app` |
   | Webhook URL | `https://your-app.ondigitalocean.app/webhook/github` |
   | Webhook secret | Generate a secure secret |

3. Set permissions:
   ```
   Repository permissions:
   ├── Checks: Read & write
   ├── Commit statuses: Read & write
   ├── Contents: Read-only
   ├── Deployments: Read-only
   └── Pull requests: Read & write
   ```

4. Subscribe to events:
   - ✅ Deployment status
   - ✅ Check suite

5. Generate and download the **Private Key**

### 2. Deploy to DigitalOcean

#### Option A: Via Dashboard

1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Click **Create App**
3. Select this repository
4. Set environment variables (see below)
5. Deploy

#### Option B: Via CLI

```bash
doctl apps create --spec .do/app.yaml
```

### 3. Set Environment Variables

Set these in the DigitalOcean Dashboard for security:

| Variable | Description |
|----------|-------------|
| `GITHUB_APP_ID` | Your GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | PEM private key (full content) |
| `GITHUB_WEBHOOK_SECRET` | Webhook secret from GitHub App |
| `OPENAI_API_KEY` | OpenAI API key for LLM analysis |

### 4. Update Webhook URL

After deployment, update your GitHub App's webhook URL:
```
https://do-deploy-analyzer-xxxxx.ondigitalocean.app/webhook/github
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/github` | POST | Receives GitHub webhooks |
| `/health` | GET | Health check |
| `/api/config/{id}` | GET | Get installation config |
| `/api/config/{id}` | POST | Update installation config |
| `/` | GET | App info |

## Local Development

```bash
# Clone the repo
git clone https://github.com/your-username/do-deploy-analyzer
cd do-deploy-analyzer

# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app:app --reload --port 8000

# Run tests
python test_app.py
```

## Example Output

When a deployment fails, users see a comment like:

```markdown
## 🚨 Deployment Failed - AI Analysis

**Environment:** `production`
**Commit:** `a1b2c3d4`

---

## 🔍 Root Cause
The deployment failed because `numpy` requires compilation 
but build-essential is missing.

## 🛠️ Suggested Fix
Add to your Dockerfile before pip install:
​```dockerfile
RUN apt-get update && apt-get install -y build-essential
​```

## 💡 Prevention Tips
- Use slim-buster instead of alpine for Python apps
- Pin package versions in requirements.txt
```

## Publishing to GitHub Marketplace

1. Ensure your repo is public
2. Go to GitHub App settings
3. Click **"List in Marketplace"**
4. Fill in listing details:
   - Description
   - Pricing (Free / Paid)
   - Categories (CI/CD, Deployment)
5. Submit for review

## Project Structure

```
do-deploy-analyzer/
├── .do/
│   └── app.yaml         # DigitalOcean deployment spec
├── app.py               # Main FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container image
├── test_app.py          # Test script
├── .env.example         # Environment template
└── README.md            # This file
```

## Tech Stack

- **FastAPI** - Web framework
- **OpenAI GPT-4** - LLM for analysis
- **PyJWT** - GitHub App authentication
- **httpx** - HTTP client

## License

MIT License - see [LICENSE](LICENSE)

## Support

- Issues: [GitHub Issues](https://github.com/your-username/do-deploy-analyzer/issues)
- Email: support@your-domain.com
