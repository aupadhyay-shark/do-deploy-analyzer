"""
DO Deploy Analyzer - GitHub App
Analyzes DigitalOcean deployment failures and posts AI-powered suggestions to GitHub.
"""

import os
import hmac
import hashlib
import httpx
import jwt
import time
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Set
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DO_API_BASE = "https://api.digitalocean.com/v2"
DIGITALOCEAN_TOKEN = os.getenv("DIGITALOCEAN_TOKEN")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
ENABLE_POLLING = os.getenv("ENABLE_POLLING", "true").lower() == "true"

# State
processed_deployments: Set[str] = set()
repo_app_mappings = {}


# =============================================================================
# Polling
# =============================================================================

async def poll_for_failed_deployments():
    """Background task that polls DO API for failed deployments."""
    logger.info(f"Starting deployment polling (interval: {POLL_INTERVAL_SECONDS}s)")
    while True:
        try:
            await check_all_apps_for_failures()
        except Exception as e:
            logger.error(f"Polling error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def check_all_apps_for_failures():
    """Check all DO apps for recent failed deployments."""
    if not DIGITALOCEAN_TOKEN:
        return
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DO_API_BASE}/apps",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"}
        )
        if response.status_code != 200:
            return
        
        for app_data in response.json().get("apps", []):
            await check_app_deployment(
                app_data.get("id"),
                app_data.get("spec", {}).get("name", "unknown")
            )


async def check_app_deployment(app_id: str, app_name: str):
    """Check a specific app for failed deployments."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"per_page": 3}
        )
        if response.status_code != 200:
            return
        
        for deployment in response.json().get("deployments", []):
            deployment_id = deployment.get("id")
            phase = deployment.get("phase", "").upper()
            
            if deployment_id in processed_deployments:
                continue
            
            # Skip old deployments (>10 minutes)
            created_at = deployment.get("created_at", "")
            if created_at:
                try:
                    deploy_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if datetime.now(deploy_time.tzinfo) - deploy_time > timedelta(minutes=10):
                        processed_deployments.add(deployment_id)
                        continue
                except:
                    pass
            
            # Check for failures
            is_failed = phase in ["ERROR", "FAILED", "CANCELED"]
            
            # Check progress steps
            for step in deployment.get("progress", {}).get("steps", []):
                if step.get("status", "").upper() in ["ERROR", "FAILED"]:
                    is_failed = True
                    break
            
            # Check runtime errors for ACTIVE deployments
            if phase == "ACTIVE":
                if await check_for_runtime_errors(app_id, deployment_id, app_name):
                    is_failed = True
            
            if is_failed:
                logger.info(f"Found failed deployment: {app_name} ({deployment_id[:8]})")
                processed_deployments.add(deployment_id)
                await process_failed_deployment(app_id, app_name, deployment)
                break


async def check_for_runtime_errors(app_id: str, deployment_id: str, app_name: str) -> bool:
    """Check if a deployment has runtime errors."""
    async with httpx.AsyncClient() as client:
        app_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"}
        )
        if app_response.status_code != 200:
            return False
        
        services = app_response.json().get("app", {}).get("spec", {}).get("services", [])
        if not services:
            return False
        
        component_name = services[0].get("name", "")
        logs_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"type": "RUN", "follow": "false"}
        )
        if logs_response.status_code != 200:
            return False
        
        logs_data = logs_response.json()
        log_content = ""
        if logs_data.get("historic_urls"):
            log_fetch = await client.get(logs_data["historic_urls"][0])
            if log_fetch.status_code == 200:
                log_content = log_fetch.text
        
        error_patterns = [
            "Error:", "ERROR:", "Exception:", "ReferenceError:", "TypeError:",
            "SyntaxError:", "ModuleNotFoundError:", "ImportError:",
            "exited with code: 1", "FATAL", "Cannot find module"
        ]
        
        for pattern in error_patterns:
            if pattern in log_content:
                logger.info(f"Runtime error in {app_name}: {pattern}")
                return True
        return False


async def process_failed_deployment(app_id: str, app_name: str, deployment: dict):
    """Process a failed deployment - analyze and post to GitHub."""
    app_info = await get_do_app_info(app_id)
    if not app_info:
        return
    
    logs = await fetch_latest_deployment_logs(app_id) or "No logs available"
    github_repo = app_info.get("github_repo")
    commit_sha = app_info.get("commit_sha", "unknown")
    
    # Check registered mappings
    if not github_repo:
        for repo, mapped_id in repo_app_mappings.items():
            if mapped_id == app_id:
                github_repo = repo
                break
    
    analysis = await analyze_deployment_failure(logs, github_repo or app_name, commit_sha)
    
    if github_repo:
        if commit_sha == "unknown":
            commit_sha = await get_latest_commit_from_github(github_repo) or "unknown"
        
        if commit_sha != "unknown":
            if await post_analysis_to_github(github_repo, commit_sha, analysis, app_name, logs[-500:]):
                logger.info(f"Posted analysis to GitHub for {app_name}")


# =============================================================================
# App Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    if ENABLE_POLLING and DIGITALOCEAN_TOKEN:
        asyncio.create_task(poll_for_failed_deployments())
        logger.info("Background polling started")
    yield


app = FastAPI(
    title="DO Deploy Analyzer",
    description="Analyzes DigitalOcean deployment failures",
    version="2.0.0",
    lifespan=lifespan
)


# =============================================================================
# GitHub Authentication
# =============================================================================

def generate_jwt_token() -> str:
    now = int(time.time())
    return jwt.encode({
        "iat": now - 60,
        "exp": now + 600,
        "iss": GITHUB_APP_ID
    }, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {generate_jwt_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
        )
        if response.status_code != 201:
            raise HTTPException(status_code=500, detail="GitHub auth failed")
        return response.json()["token"]


async def find_installation_for_repo(owner: str, repo: str) -> Optional[int]:
    if not GITHUB_APP_ID or not GITHUB_APP_PRIVATE_KEY:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/app/installations",
            headers={
                "Authorization": f"Bearer {generate_jwt_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
        )
        if response.status_code != 200:
            return None
        
        for installation in response.json():
            if installation.get("account", {}).get("login", "").lower() == owner.lower():
                return installation.get("id")
        
        for installation in response.json():
            try:
                token = await get_installation_token(installation.get("id"))
                repo_response = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
                )
                if repo_response.status_code == 200:
                    return installation.get("id")
            except:
                continue
    return None


async def get_latest_commit_from_github(repo: str) -> Optional[str]:
    parts = repo.split("/")
    if len(parts) != 2:
        return None
    
    installation_id = await find_installation_for_repo(parts[0], parts[1])
    if not installation_id:
        return None
    
    try:
        token = await get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{parts[0]}/{parts[1]}/commits",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                params={"per_page": 1}
            )
            if response.status_code == 200 and response.json():
                return response.json()[0].get("sha")
    except:
        pass
    return None


# =============================================================================
# LLM Analysis
# =============================================================================

async def analyze_deployment_failure(logs: str, repo_name: str, commit_sha: str) -> str:
    if not OPENAI_API_KEY:
        return "LLM analysis unavailable - OpenAI API key not configured"
    
    prompt = f"""Analyze this DigitalOcean deployment failure:

Repository: {repo_name}
Commit: {commit_sha[:8] if commit_sha != "unknown" else "unknown"}

Logs:
```
{logs[-6000:]}
```

Provide:
## Root Cause
[What went wrong]

## Suggested Fix
[How to fix it]

## Prevention Tips
[How to prevent this]

Keep it concise and actionable."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a DevOps expert."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1500,
                "temperature": 0.3
            },
            timeout=60.0
        )
        if response.status_code != 200:
            return "Failed to analyze deployment"
        return response.json()["choices"][0]["message"]["content"]


# =============================================================================
# GitHub Posting
# =============================================================================

async def post_analysis_to_github(repo: str, commit_sha: str, analysis: str, app_name: str, logs_snippet: str) -> bool:
    parts = repo.split("/")
    if len(parts) != 2:
        return False
    
    owner, repo_name = parts
    installation_id = await find_installation_for_repo(owner, repo_name)
    if not installation_id:
        return False
    
    try:
        token = await get_installation_token(installation_id)
    except:
        return False
    
    comment_body = f"""## 🚨 Deployment Failed - AI Analysis

**App:** `{app_name}`
**Commit:** `{commit_sha[:8]}`
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

---

{analysis}

---

<details>
<summary>Log Snippet</summary>

```
{logs_snippet}
```

</details>

---
*Powered by DO Deploy Analyzer*
"""
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/commits/{commit_sha}/comments",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            json={"body": comment_body}
        )
        return response.status_code == 201


# =============================================================================
# DigitalOcean API
# =============================================================================

async def get_do_app_info(app_id: str) -> Optional[dict]:
    if not DIGITALOCEAN_TOKEN or not app_id:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"}
        )
        if response.status_code != 200:
            return None
        
        app_data = response.json().get("app", {})
        spec = app_data.get("spec", {})
        app_name = spec.get("name", "")
        
        github_repo = None
        for component_type in ["services", "workers", "jobs", "static_sites", "functions"]:
            if github_repo:
                break
            for component in spec.get(component_type, []):
                github = component.get("github", {})
                if github.get("repo"):
                    github_repo = github.get("repo")
                    break
                git = component.get("git", {})
                if git and "github.com" in git.get("repo_clone_url", ""):
                    url = git["repo_clone_url"].replace("https://", "").replace(".git", "")
                    if "github.com/" in url:
                        github_repo = url.split("github.com/")[1]
                        break
        
        commit_sha = None
        dep_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"per_page": 1}
        )
        if dep_response.status_code == 200:
            deployments = dep_response.json().get("deployments", [])
            if deployments:
                cause = deployments[0].get("cause", {})
                if isinstance(cause, dict):
                    commit_sha = cause.get("commit_sha") or cause.get("git_sha")
        
        return {"github_repo": github_repo, "commit_sha": commit_sha or "unknown", "app_name": app_name}


async def fetch_latest_deployment_logs(app_id: str) -> Optional[str]:
    if not DIGITALOCEAN_TOKEN:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}/deployments",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
            params={"per_page": 5}
        )
        if response.status_code != 200:
            return None
        
        deployments = response.json().get("deployments", [])
        deployment = next((d for d in deployments if d.get("phase") in ["ERROR", "FAILED"]), None)
        deployment = deployment or (deployments[0] if deployments else None)
        if not deployment:
            return None
        
        app_response = await client.get(
            f"{DO_API_BASE}/apps/{app_id}",
            headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"}
        )
        if app_response.status_code != 200:
            return None
        
        services = app_response.json().get("app", {}).get("spec", {}).get("services", [])
        if not services:
            return None
        
        component_name = services[0].get("name", "")
        deployment_id = deployment.get("id")
        
        for log_type in ["BUILD", "RUN"]:
            logs_response = await client.get(
                f"{DO_API_BASE}/apps/{app_id}/deployments/{deployment_id}/components/{component_name}/logs",
                headers={"Authorization": f"Bearer {DIGITALOCEAN_TOKEN}"},
                params={"type": log_type, "follow": "false"}
            )
            if logs_response.status_code == 200:
                logs_data = logs_response.json()
                if logs_data.get("historic_urls"):
                    log_content = await client.get(logs_data["historic_urls"][0])
                    if log_content.status_code == 200:
                        return log_content.text
        return None


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "github_configured": bool(GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY),
        "openai_configured": bool(OPENAI_API_KEY),
        "do_configured": bool(DIGITALOCEAN_TOKEN)
    }


@app.get("/")
async def root():
    return {"name": "DO Deploy Analyzer", "docs": "/docs"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256")
):
    payload = await request.body()
    
    if x_hub_signature_256 and GITHUB_WEBHOOK_SECRET:
        expected = "sha256=" + hmac.new(GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = await request.json()
    logger.info(f"GitHub event: {x_github_event}")
    
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event == "installation":
        logger.info(f"App {'installed' if data.get('action') == 'created' else 'uninstalled'}")
        return {"status": "ok"}
    
    return {"status": "ignored"}


class AnalyzeRequest(BaseModel):
    repo: str
    logs: Optional[str] = None
    do_app_id: Optional[str] = None


@app.post("/analyze")
async def analyze_endpoint(request: AnalyzeRequest):
    logs = request.logs
    if not logs and request.do_app_id:
        logs = await fetch_latest_deployment_logs(request.do_app_id)
    if not logs:
        return {"status": "error", "message": "No logs provided"}
    
    analysis = await analyze_deployment_failure(logs, request.repo, "unknown")
    return {"status": "analyzed", "analysis": analysis}


@app.post("/register-repo")
async def register_repo(repo: str, do_app_id: str):
    repo_app_mappings[repo] = do_app_id
    return {"status": "registered", "repo": repo, "do_app_id": do_app_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
