"""
DO Deploy Analyzer - GitHub App
A GitHub Marketplace app that analyzes DigitalOcean deployment failures
and posts helpful suggestions as comments.
"""

import os
import hmac
import hashlib
import httpx
import jwt
import time
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="DO Deploy Analyzer",
    description="GitHub App that analyzes DigitalOcean deployment failures",
    version="1.0.0"
)

# =============================================================================
# Configuration
# =============================================================================

# GitHub App credentials (from GitHub Developer Settings)
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# OpenAI for LLM analysis
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# DigitalOcean API (optional - for fetching logs if user provides token)
DO_API_BASE = "https://api.digitalocean.com/v2"


# =============================================================================
# GitHub App Authentication
# =============================================================================

def generate_jwt_token() -> str:
    """
    Generate a JWT token for GitHub App authentication.
    This is used to authenticate as the GitHub App itself.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued at time (60 seconds in the past for clock drift)
        "exp": now + (10 * 60),  # Expiration time (10 minutes)
        "iss": GITHUB_APP_ID  # GitHub App ID
    }
    
    return jwt.encode(payload, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """
    Get an installation access token for a specific installation.
    This token is used to act on behalf of the installation (user's repo).
    """
    jwt_token = generate_jwt_token()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
        )
        
        if response.status_code != 201:
            logger.error(f"Failed to get installation token: {response.text}")
            raise HTTPException(status_code=500, detail="Failed to authenticate with GitHub")
        
        return response.json()["token"]


# =============================================================================
# Webhook Signature Verification
# =============================================================================

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify that the webhook payload came from GitHub."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set, skipping verification")
        return True
    
    expected_signature = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


# =============================================================================
# LLM Analysis
# =============================================================================

async def analyze_deployment_failure(
    logs: str,
    repo_name: str,
    commit_sha: str,
    deployment_env: str
) -> str:
    """
    Analyze deployment failure logs using LLM.
    Returns a markdown-formatted analysis.
    """
    if not OPENAI_API_KEY:
        return "⚠️ LLM analysis unavailable - OpenAI API key not configured"
    
    prompt = f"""You are a DevOps expert analyzing a DigitalOcean App Platform deployment failure.

Repository: {repo_name}
Commit: {commit_sha[:8]}
Environment: {deployment_env}

Deployment Logs:
```
{logs[-6000:]}
```

Analyze this failure and provide:

## 🔍 Root Cause
[Brief description of what went wrong]

## 🛠️ Suggested Fix
[Step-by-step fix instructions]

## 📚 Related Documentation
[Links to relevant docs if applicable]

## 💡 Prevention Tips
[How to prevent this in the future]

Keep the response concise and actionable. Use code blocks for any commands or code changes."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a helpful DevOps assistant specializing in DigitalOcean deployments."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1500,
                "temperature": 0.3
            },
            timeout=60.0
        )
        
        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.text}")
            return "⚠️ Failed to analyze deployment - LLM service unavailable"
        
        return response.json()["choices"][0]["message"]["content"]


# =============================================================================
# GitHub API Interactions
# =============================================================================

async def post_commit_comment(
    installation_token: str,
    owner: str,
    repo: str,
    commit_sha: str,
    body: str
):
    """Post a comment on a specific commit."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}/comments",
            headers={
                "Authorization": f"Bearer {installation_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            json={"body": body}
        )
        
        if response.status_code != 201:
            logger.error(f"Failed to post comment: {response.text}")
            return False
        
        logger.info(f"Posted comment on {owner}/{repo}@{commit_sha[:8]}")
        return True


async def create_check_run(
    installation_token: str,
    owner: str,
    repo: str,
    commit_sha: str,
    name: str,
    status: str,
    conclusion: str,
    output: dict
):
    """Create a check run with detailed output (shows in PR checks)."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/check-runs",
            headers={
                "Authorization": f"Bearer {installation_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            json={
                "name": name,
                "head_sha": commit_sha,
                "status": status,
                "conclusion": conclusion,
                "output": output
            }
        )
        
        if response.status_code != 201:
            logger.error(f"Failed to create check run: {response.text}")
            return False
        
        logger.info(f"Created check run on {owner}/{repo}@{commit_sha[:8]}")
        return True


async def get_deployment_logs_from_do(
    do_token: str,
    app_id: str,
    deployment_id: str
) -> Optional[str]:
    """
    Fetch deployment logs from DigitalOcean API.
    Requires user's DO token (stored securely per installation).
    """
    async with httpx.AsyncClient() as client:
        # First, get the component name
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}",
            headers={"Authorization": f"Bearer {do_token}"}
        )
        
        if response.status_code != 200:
            return None
        
        app_data = response.json().get("app", {})
        components = app_data.get("spec", {}).get("services", [])
        
        if not components:
            return None
        
        component_name = components[0].get("name", "")
        
        # Get logs
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs",
            headers={"Authorization": f"Bearer {do_token}"},
            params={"type": "BUILD", "follow": "false"}
        )
        
        if response.status_code != 200:
            return None
        
        logs_data = response.json()
        
        # Extract log lines
        if "historic_urls" in logs_data:
            # Fetch from historic URL
            log_url = logs_data["historic_urls"][0]
            log_response = await client.get(log_url)
            return log_response.text if log_response.status_code == 200 else None
        
        return None


# =============================================================================
# Database for storing user configurations
# =============================================================================

# In production, use a proper database (PostgreSQL, MongoDB, etc.)
# This is a simple in-memory store for demonstration
installation_configs = {}


class InstallationConfig(BaseModel):
    installation_id: int
    do_token: Optional[str] = None  # Encrypted in production
    notification_email: Optional[str] = None
    enabled: bool = True


# =============================================================================
# Webhook Endpoints
# =============================================================================

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256")
):
    """
    Main webhook endpoint that receives events from GitHub.
    Handles: installation, deployment_status, check_suite
    """
    payload = await request.body()
    
    # Verify webhook signature
    if x_hub_signature_256 and not verify_webhook_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = await request.json()
    
    logger.info(f"Received GitHub event: {x_github_event}")
    
    # Route to appropriate handler
    if x_github_event == "installation":
        return await handle_installation(data)
    elif x_github_event == "deployment_status":
        return await handle_deployment_status(data)
    elif x_github_event == "check_suite":
        return await handle_check_suite(data)
    elif x_github_event == "ping":
        return {"status": "pong"}
    else:
        logger.info(f"Ignoring event: {x_github_event}")
        return {"status": "ignored"}


async def handle_installation(data: dict):
    """Handle app installation/uninstallation events."""
    action = data.get("action")
    installation = data.get("installation", {})
    installation_id = installation.get("id")
    
    if action == "created":
        # New installation - store configuration
        installation_configs[installation_id] = InstallationConfig(
            installation_id=installation_id
        )
        logger.info(f"App installed: installation_id={installation_id}")
        
        # Optionally: Send welcome message or setup instructions
        
    elif action == "deleted":
        # App uninstalled - remove configuration
        if installation_id in installation_configs:
            del installation_configs[installation_id]
        logger.info(f"App uninstalled: installation_id={installation_id}")
    
    return {"status": "ok"}


async def handle_deployment_status(data: dict):
    """
    Handle deployment_status events.
    This is triggered when DigitalOcean updates deployment status via GitHub.
    """
    deployment_status = data.get("deployment_status", {})
    deployment = data.get("deployment", {})
    repository = data.get("repository", {})
    installation = data.get("installation", {})
    
    state = deployment_status.get("state")
    environment = deployment.get("environment", "unknown")
    
    # Only process failures
    if state not in ["failure", "error"]:
        logger.info(f"Deployment state '{state}' - not a failure, skipping")
        return {"status": "skipped", "reason": "not a failure"}
    
    # Check if this is a DigitalOcean deployment
    # DO deployments typically have specific environment naming or creator info
    creator = deployment_status.get("creator", {})
    description = deployment_status.get("description", "")
    
    # Get repository info
    owner = repository.get("owner", {}).get("login")
    repo = repository.get("name")
    commit_sha = deployment.get("sha")
    installation_id = installation.get("id")
    
    logger.info(f"Processing failed deployment: {owner}/{repo}@{commit_sha[:8]}")
    
    # Get installation token
    try:
        installation_token = await get_installation_token(installation_id)
    except Exception as e:
        logger.error(f"Failed to get installation token: {e}")
        return {"status": "error", "message": "Authentication failed"}
    
    # Try to get deployment logs
    logs = None
    config = installation_configs.get(installation_id)
    
    if config and config.do_token:
        # If user has connected their DO account, fetch actual logs
        # This requires storing the DO app_id mapping (future enhancement)
        pass
    
    # If no logs available, use the deployment status description
    logs = description or "No detailed logs available. Check DigitalOcean dashboard for full logs."
    
    # Generate analysis
    analysis = await analyze_deployment_failure(
        logs=logs,
        repo_name=f"{owner}/{repo}",
        commit_sha=commit_sha,
        deployment_env=environment
    )
    
    # Create the comment body
    comment_body = f"""## 🚨 Deployment Failed - AI Analysis

**Environment:** `{environment}`
**Commit:** `{commit_sha[:8]}`
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

---

{analysis}

---

<details>
<summary>📋 Deployment Status Details</summary>

```
State: {state}
Description: {description}
```

</details>

---
*Powered by [DO Deploy Analyzer](https://github.com/marketplace/do-deploy-analyzer) - Automatic deployment failure analysis*
"""
    
    # Post comment on the commit
    await post_commit_comment(
        installation_token=installation_token,
        owner=owner,
        repo=repo,
        commit_sha=commit_sha,
        body=comment_body
    )
    
    # Also create a check run for better visibility in PRs
    await create_check_run(
        installation_token=installation_token,
        owner=owner,
        repo=repo,
        commit_sha=commit_sha,
        name="DO Deploy Analyzer",
        status="completed",
        conclusion="failure",
        output={
            "title": "Deployment Analysis",
            "summary": f"Deployment to `{environment}` failed. See analysis below.",
            "text": analysis
        }
    )
    
    return {"status": "analyzed", "commit": commit_sha[:8]}


async def handle_check_suite(data: dict):
    """Handle check_suite events (for re-run requests)."""
    action = data.get("action")
    
    if action == "rerequested":
        # User requested to re-run checks
        # Could re-analyze if needed
        pass
    
    return {"status": "ok"}


# =============================================================================
# Configuration API (for user settings)
# =============================================================================

@app.get("/api/config/{installation_id}")
async def get_config(installation_id: int):
    """Get configuration for an installation."""
    config = installation_configs.get(installation_id)
    if not config:
        raise HTTPException(status_code=404, detail="Installation not found")
    
    return {
        "installation_id": config.installation_id,
        "enabled": config.enabled,
        "has_do_token": bool(config.do_token),
        "notification_email": config.notification_email
    }


@app.post("/api/config/{installation_id}")
async def update_config(installation_id: int, config_update: dict):
    """Update configuration for an installation."""
    if installation_id not in installation_configs:
        installation_configs[installation_id] = InstallationConfig(
            installation_id=installation_id
        )
    
    config = installation_configs[installation_id]
    
    if "enabled" in config_update:
        config.enabled = config_update["enabled"]
    if "do_token" in config_update:
        # In production: encrypt before storing
        config.do_token = config_update["do_token"]
    if "notification_email" in config_update:
        config.notification_email = config_update["notification_email"]
    
    return {"status": "updated"}


@app.post("/api/config/{installation_id}/connect-do")
async def connect_digitalocean(installation_id: int, do_token: str):
    """
    Connect DigitalOcean account to enable log fetching.
    In production, use OAuth flow instead of direct token.
    """
    # Verify the token works
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DO_API_BASE}/apps",
            headers={"Authorization": f"Bearer {do_token}"}
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid DigitalOcean token")
    
    if installation_id not in installation_configs:
        installation_configs[installation_id] = InstallationConfig(
            installation_id=installation_id
        )
    
    installation_configs[installation_id].do_token = do_token
    
    return {"status": "connected"}


# =============================================================================
# DigitalOcean Direct Integration
# =============================================================================

# DigitalOcean token for fetching logs (set via env var)
DIGITALOCEAN_TOKEN = os.getenv("DIGITALOCEAN_TOKEN")

# Store repo -> DO app mappings
repo_app_mappings = {}


class AnalyzeRequest(BaseModel):
    repo: str  # e.g., "owner/repo"
    commit_sha: Optional[str] = None
    logs: Optional[str] = None
    do_app_id: Optional[str] = None


@app.post("/analyze")
async def analyze_deployment(request: AnalyzeRequest):
    """
    Direct endpoint to analyze deployment failures.
    Can be called:
    1. Manually with logs
    2. From DigitalOcean alerts
    3. With DO app_id to fetch logs automatically
    """
    logger.info(f"Analyze request for repo: {request.repo}")
    
    logs = request.logs
    
    # If no logs provided but DO app_id given, fetch from DO API
    if not logs and request.do_app_id and DIGITALOCEAN_TOKEN:
        logs = await fetch_latest_deployment_logs(request.do_app_id)
    
    if not logs:
        return {"status": "error", "message": "No logs provided and unable to fetch from DO"}
    
    # Parse repo
    parts = request.repo.split("/")
    if len(parts) != 2:
        return {"status": "error", "message": "Invalid repo format. Use 'owner/repo'"}
    
    owner, repo = parts
    commit_sha = request.commit_sha or "unknown"
    
    # Analyze with LLM
    analysis = await analyze_deployment_failure(
        logs=logs,
        repo_name=request.repo,
        commit_sha=commit_sha,
        deployment_env="digitalocean"
    )
    
    return {
        "status": "analyzed",
        "repo": request.repo,
        "analysis": analysis
    }


@app.post("/webhook/digitalocean")
async def digitalocean_webhook(request: Request):
    """
    Receive webhooks directly from DigitalOcean alerts.
    Configure DO alerts to POST to this endpoint on deployment failures.
    """
    try:
        data = await request.json()
    except:
        data = {}
    
    logger.info(f"Received DO webhook: {data}")
    
    # Extract info from DO alert payload
    alert_type = data.get("alert_type", "")
    app_name = data.get("app_name", "")
    app_id = data.get("app_id", "")
    
    # Check if this is a deployment failure
    if "DEPLOYMENT_FAILED" in str(data) or "failed" in str(data).lower():
        logger.info(f"Deployment failure detected for app: {app_name}")
        
        # Try to fetch logs if we have the app_id
        if app_id and DIGITALOCEAN_TOKEN:
            logs = await fetch_latest_deployment_logs(app_id)
            
            if logs:
                analysis = await analyze_deployment_failure(
                    logs=logs,
                    repo_name=app_name or "unknown",
                    commit_sha="unknown",
                    deployment_env="digitalocean"
                )
                
                return {
                    "status": "analyzed",
                    "app": app_name,
                    "analysis": analysis
                }
    
    return {"status": "received", "data": data}


async def fetch_latest_deployment_logs(app_id: str) -> Optional[str]:
    """Fetch logs from the latest failed deployment."""
    if not DIGITALOCEAN_TOKEN:
        return None
    
    async with httpx.AsyncClient() as client:
        # Get latest deployments
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"per_page": 5}
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch deployments: {response.text}")
            return None
        
        deployments = response.json().get("deployments", [])
        
        # Find latest failed deployment
        failed_deployment = None
        for dep in deployments:
            if dep.get("phase") in ["ERROR", "FAILED"]:
                failed_deployment = dep
                break
        
        if not failed_deployment:
            # Use the latest deployment
            failed_deployment = deployments[0] if deployments else None
        
        if not failed_deployment:
            return None
        
        deployment_id = failed_deployment.get("id")
        
        # Get app spec to find component name
        app_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"}
        )
        
        if app_response.status_code != 200:
            return None
        
        app_data = app_response.json().get("app", {})
        services = app_data.get("spec", {}).get("services", [])
        
        if not services:
            return None
        
        component_name = services[0].get("name", "")
        
        # Fetch build logs
        logs_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"type": "BUILD", "follow": "false"}
        )
        
        if logs_response.status_code != 200:
            # Try RUN logs
            logs_response = await client.get(
                f"{DO_API_BASE}/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs",
                headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
                params={"type": "RUN", "follow": "false"}
            )
        
        if logs_response.status_code != 200:
            return None
        
        logs_data = logs_response.json()
        
        # Get logs from historic URL if available
        if "historic_urls" in logs_data and logs_data["historic_urls"]:
            log_url = logs_data["historic_urls"][0]
            log_content = await client.get(log_url)
            if log_content.status_code == 200:
                return log_content.text
        
        return str(logs_data)


@app.post("/register-repo")
async def register_repo(repo: str, do_app_id: str):
    """Register a GitHub repo to a DigitalOcean app for automatic analysis."""
    repo_app_mappings[repo] = do_app_id
    logger.info(f"Registered {repo} -> {do_app_id}")
    return {"status": "registered", "repo": repo, "do_app_id": do_app_id}


@app.get("/registered-repos")
async def list_registered_repos():
    """List all registered repo -> DO app mappings."""
    return {"mappings": repo_app_mappings}


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "github_app_configured": bool(GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY),
        "openai_configured": bool(OPENAI_API_KEY),
        "do_token_configured": bool(DIGITALOCEAN_TOKEN)
    }


@app.get("/")
async def root():
    return {
        "name": "DO Deploy Analyzer",
        "description": "GitHub App for analyzing DigitalOcean deployment failures",
        "docs": "/docs",
        "github_app": "https://github.com/marketplace/do-deploy-analyzer"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
