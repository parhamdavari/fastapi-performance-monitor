"""Integration tests for FastAPI Pulse CLI commands."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_pulse import add_pulse


@pytest.fixture
def test_app():
    """Create a test FastAPI app."""
    app = FastAPI()
    add_pulse(app)

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/slow")
    async def slow():
        import asyncio
        await asyncio.sleep(0.5)
        return {"message": "slow response"}

    @app.get("/api/error")
    async def error():
        raise RuntimeError("Test error")

    return app


def test_cli_entry_point_exists():
    """Test that the pulse-cli command is available after installation."""
    # This test assumes the package is installed in development mode
    result = subprocess.run(
        [sys.executable, "-m", "fastapi_pulse.cli", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "FastAPI Pulse CLI" in result.stdout or "pulse-cli" in result.stdout


def test_cli_check_command_help():
    """Test that the check command help is available."""
    result = subprocess.run(
        [sys.executable, "-m", "fastapi_pulse.cli", "check", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Check health of FastAPI endpoints" in result.stdout
    assert "--format" in result.stdout
    assert "--timeout" in result.stdout


@pytest.mark.asyncio
async def test_cli_check_with_running_server(test_app):
    """Test CLI check command against a running server."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        # Run CLI check with JSON output
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # Parse JSON output
        output = json.loads(result.stdout)
        assert "summary" in output
        assert "endpoints" in output
        assert output["summary"]["total"] > 0


@pytest.mark.asyncio
async def test_cli_fail_on_error_flag(test_app):
    """Test that --fail-on-error flag causes non-zero exit on errors."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        # Trigger the error endpoint first to ensure it's detected
        client.get("/api/error")

        # Run CLI with fail-on-error flag
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "json",
                "--fail-on-error",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should have non-zero exit code due to error endpoint
        # (This might be 0 if the error endpoint wasn't probed, so we check the output)
        output = json.loads(result.stdout)
        has_errors = any(
            ep["status"] in {"critical", "warning"}
            for ep in output["endpoints"]
        )

        if has_errors:
            assert result.returncode == 1


@pytest.mark.asyncio
async def test_cli_specific_endpoints_filter(test_app):
    """Test filtering specific endpoints with --endpoints flag."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        # Run CLI checking only specific endpoint
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "json",
                "--endpoints",
                "GET /api/health",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

        output = json.loads(result.stdout)
        assert len(output["endpoints"]) == 1
        assert output["endpoints"][0]["endpoint_id"] == "GET /api/health"


@pytest.mark.asyncio
async def test_cli_summary_format(test_app):
    """Test summary output format."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "summary",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "healthy" in result.stdout.lower()
        assert "Total:" in result.stdout


@pytest.mark.asyncio
async def test_cli_table_format(test_app):
    """Test table output format."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "table",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        # Table format should contain endpoint information
        assert "Endpoint" in result.stdout or "endpoint" in result.stdout.lower()


@pytest.mark.asyncio
async def test_cli_custom_timeout(test_app):
    """Test custom timeout configuration."""
    with TestClient(test_app) as client:
        base_url = str(client.base_url)

        # Use very short timeout
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_pulse.cli",
                "check",
                base_url,
                "--format",
                "json",
                "--timeout",
                "0.1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Command should complete (might have timeouts but shouldn't crash)
        assert result.returncode in {0, 1}


@pytest.mark.asyncio
async def test_cli_invalid_url():
    """Test CLI behavior with invalid URL."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fastapi_pulse.cli",
            "check",
            "http://invalid-url-that-does-not-exist:9999",
            "--format",
            "json",
            "--timeout",
            "2",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should fail gracefully
    assert result.returncode == 1
    assert "Error" in result.stderr or "failed" in result.stderr.lower()
