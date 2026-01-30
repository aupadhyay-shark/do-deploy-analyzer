"""
Test script for DO Deploy Analyzer GitHub App
Simulates GitHub webhook events locally
"""

import httpx
import hmac
import hashlib
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
APP_URL = os.getenv("TEST_APP_URL", "http://localhost:8000")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "test-secret")


def generate_signature(payload: bytes) -> str:
    """Generate GitHub-style webhook signature."""
    return "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


def test_ping():
    """Test ping event (sent when webhook is configured)."""
    print("\n" + "="*60)
    print("Testing: Ping Event")
    print("="*60)
    
    payload = {"zen": "Responsive is better than fast.", "hook_id": 12345}
    payload_bytes = json.dumps(payload).encode()
    
    response = httpx.post(
        f"{APP_URL}/webhook/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": generate_signature(payload_bytes)
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    return response.status_code == 200


def test_installation():
    """Test installation event (when user installs the app)."""
    print("\n" + "="*60)
    print("Testing: Installation Event")
    print("="*60)
    
    payload = {
        "action": "created",
        "installation": {
            "id": 12345678,
            "account": {
                "login": "test-user",
                "type": "User"
            }
        },
        "repositories": [
            {"name": "test-repo", "full_name": "test-user/test-repo"}
        ]
    }
    payload_bytes = json.dumps(payload).encode()
    
    response = httpx.post(
        f"{APP_URL}/webhook/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "installation",
            "X-Hub-Signature-256": generate_signature(payload_bytes)
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    return response.status_code == 200


def test_deployment_success():
    """Test successful deployment (should be skipped)."""
    print("\n" + "="*60)
    print("Testing: Deployment Success (should skip)")
    print("="*60)
    
    payload = {
        "action": "created",
        "deployment_status": {
            "state": "success",
            "description": "Deployment successful"
        },
        "deployment": {
            "sha": "abc123def456",
            "environment": "production"
        },
        "repository": {
            "name": "test-repo",
            "owner": {"login": "test-user"}
        },
        "installation": {"id": 12345678}
    }
    payload_bytes = json.dumps(payload).encode()
    
    response = httpx.post(
        f"{APP_URL}/webhook/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "deployment_status",
            "X-Hub-Signature-256": generate_signature(payload_bytes)
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Should return "skipped" since it's not a failure
    return response.status_code == 200 and response.json().get("status") == "skipped"


def test_deployment_failure():
    """Test failed deployment (should trigger analysis)."""
    print("\n" + "="*60)
    print("Testing: Deployment Failure (should analyze)")
    print("="*60)
    
    payload = {
        "action": "created",
        "deployment_status": {
            "state": "failure",
            "description": "Build failed: ERROR: Could not find a version that satisfies the requirement numpy==999.0.0",
            "creator": {
                "login": "digitalocean",
                "type": "Bot"
            }
        },
        "deployment": {
            "sha": "a1b2c3d4e5f6789",
            "environment": "production",
            "ref": "main"
        },
        "repository": {
            "name": "my-app",
            "full_name": "test-user/my-app",
            "owner": {"login": "test-user"}
        },
        "installation": {"id": 12345678}
    }
    payload_bytes = json.dumps(payload).encode()
    
    print("Sending deployment failure event...")
    print("Note: This will attempt to post a comment to GitHub (will fail without valid token)")
    
    try:
        response = httpx.post(
            f"{APP_URL}/webhook/github",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "deployment_status",
                "X-Hub-Signature-256": generate_signature(payload_bytes)
            },
            timeout=120.0  # LLM analysis can take time
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_health():
    """Test health endpoint."""
    print("\n" + "="*60)
    print("Testing: Health Check")
    print("="*60)
    
    response = httpx.get(f"{APP_URL}/health")
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 200


def test_config_api():
    """Test configuration API."""
    print("\n" + "="*60)
    print("Testing: Configuration API")
    print("="*60)
    
    installation_id = 12345678
    
    # Get config (may 404 if not installed)
    response = httpx.get(f"{APP_URL}/api/config/{installation_id}")
    print(f"GET config status: {response.status_code}")
    
    if response.status_code == 200:
        print(f"Config: {response.json()}")
    
    # Update config
    response = httpx.post(
        f"{APP_URL}/api/config/{installation_id}",
        json={"enabled": True, "notification_email": "test@example.com"}
    )
    print(f"POST config status: {response.status_code}")
    
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# DO Deploy Analyzer - GitHub App Tests")
    print("#"*60)
    print(f"\nTarget: {APP_URL}")
    
    results = {
        "Health Check": test_health(),
        "Ping Event": test_ping(),
        "Installation Event": test_installation(),
        "Config API": test_config_api(),
        "Deployment Success": test_deployment_success(),
        # Skip failure test by default as it needs OpenAI key
        # "Deployment Failure": test_deployment_failure(),
    }
    
    # Ask if user wants to test deployment failure
    print("\n" + "="*60)
    print("Skip deployment failure test? (requires OpenAI key)")
    print("="*60)
    
    user_input = input("Run deployment failure test? (y/N): ").strip().lower()
    if user_input == 'y':
        results["Deployment Failure"] = test_deployment_failure()
    else:
        results["Deployment Failure"] = "SKIPPED"
    
    # Summary
    print("\n" + "#"*60)
    print("# Test Results")
    print("#"*60)
    
    for test_name, result in results.items():
        if result == "SKIPPED":
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{status}: {test_name}")


if __name__ == "__main__":
    run_all_tests()
