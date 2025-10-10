"""Unit tests for internal helpers in fastapi_pulse.cli.commands."""

from __future__ import annotations

import asyncio
import types
import sys
from pathlib import Path

import pytest

from fastapi_pulse.cli import commands
from fastapi_pulse.cli.standalone_probe import EndpointProbeResult


def test_parse_headers_handles_invalid(capsys):
    headers = commands._parse_headers(("X-Test: 1", "invalid-header"))
    captured = capsys.readouterr()
    assert headers == {"X-Test": "1"}
    assert "Invalid header format" in captured.err


def test_merge_config_cli_overrides():
    file_config = {
        "base_url": "http://file",
        "timeout": 20,
        "output": {"format": "summary"},
        "auth": {"headers": {"X-Token": "abc"}},
        "concurrency": 4,
        "endpoints": {"include": ["GET /file"]},
        "transport": {"asgi_app": "module:attr"},
    }

    merged = commands._merge_config(
        file_config,
        base_url="http://cli",
        timeout=5,
        output_format="json",
        custom_headers=("X-CLI: 1",),
        concurrency=2,
        endpoints=("GET /cli",),
    )

    assert merged["base_url"] == "http://cli"
    # File config timeout and output format are retained because CLI does not override them explicitly
    assert merged["timeout"] == 20
    assert merged["output_format"] == "summary"
    assert merged["custom_headers"] == ("X-CLI: 1",)
    assert merged["concurrency"] == 4
    assert merged["endpoints"] == ["GET /cli"]
    assert merged["asgi_app"] == "module:attr"


def test_load_config_success(tmp_path: Path):
    cfg = tmp_path / "pulse.yaml"
    cfg.write_text(
        """
base_url: http://file
timeout: 15
output:
  format: table
auth:
  headers:
    X-Token: secret
concurrency: 3
endpoints:
  include:
    - GET /foo
transport:
  asgi_app: tests.cli.test_cli_integration:create_test_app
"""
    )
    data = commands._load_config(cfg)
    assert data["base_url"] == "http://file"
    assert data["timeout"] == 15
    assert data["output"]["format"] == "table"
    assert data["auth"]["headers"]["X-Token"] == "secret"
    assert data["transport"]["asgi_app"].endswith("create_test_app")


def test_load_config_handles_error(tmp_path: Path, capsys):
    cfg_dir = tmp_path / "config_dir"
    cfg_dir.mkdir()
    data = commands._load_config(cfg_dir)
    captured = capsys.readouterr()
    assert data == {}
    assert "Failed to load config file" in captured.err


def test_load_asgi_app_variants(monkeypatch):
    module = types.ModuleType("tests.sample_asgi")

    class DummyApp:
        pass

    module.app = DummyApp()

    def factory():
        return DummyApp()

    async def async_factory():
        return DummyApp()

    module.factory = factory
    module.async_factory = async_factory
    sys.modules["tests.sample_asgi"] = module

    assert isinstance(commands._load_asgi_app("tests.sample_asgi:app"), DummyApp)
    assert isinstance(commands._load_asgi_app("tests.sample_asgi:factory"), DummyApp)
    assert isinstance(commands._load_asgi_app("tests.sample_asgi:async_factory"), DummyApp)

    with pytest.raises(AttributeError):
        commands._load_asgi_app("tests.sample_asgi:missing")

    with pytest.raises(ValueError):
        commands._load_asgi_app("tests.sample_asgi")


@pytest.mark.asyncio
async def test_run_probe_happy_path(monkeypatch):
    class StubClient:
        def __init__(self, **_):
            pass

        async def fetch_endpoints(self):
            return [
                {
                    "id": "GET /ok",
                    "method": "GET",
                    "path": "/ok",
                    "payload": {"effective": {"path_params": {}, "headers": {}, "query": {}, "body": None}},
                }
            ]

        async def probe_endpoints(self, endpoints):
            assert endpoints[0]["id"] == "GET /ok"
            return [
                EndpointProbeResult(
                    endpoint_id="GET /ok",
                    method="GET",
                    path="/ok",
                    status="healthy",
                    status_code=200,
                    latency_ms=10.0,
                )
            ]

    monkeypatch.setattr(commands, "StandaloneProbeClient", StubClient)

    exit_code = await commands._run_probe(
        base_url="http://test",
        timeout=1.0,
        headers={},
        concurrency=1,
        specific_endpoints=[],
        output_format="json",
        fail_on_error=False,
    )
    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_probe_fail_on_error(monkeypatch):
    class StubClient:
        def __init__(self, **_):
            pass

        async def fetch_endpoints(self):
            return [
                {
                    "id": "GET /bad",
                    "method": "GET",
                    "path": "/bad",
                    "payload": {"effective": {"path_params": {}, "headers": {}, "query": {}, "body": None}},
                }
            ]

        async def probe_endpoints(self, _):
            return [
                EndpointProbeResult(
                    endpoint_id="GET /bad",
                    method="GET",
                    path="/bad",
                    status="critical",
                    status_code=500,
                    latency_ms=42.0,
                )
            ]

    monkeypatch.setattr(commands, "StandaloneProbeClient", StubClient)

    exit_code = await commands._run_probe(
        base_url="http://test",
        timeout=1.0,
        headers={},
        concurrency=1,
        specific_endpoints=[],
        output_format="summary",
        fail_on_error=True,
    )
    assert exit_code == 1


@pytest.mark.asyncio
async def test_run_probe_handles_exception(monkeypatch, capsys):
    class StubClient:
        def __init__(self, **_):
            pass

        async def fetch_endpoints(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(commands, "StandaloneProbeClient", StubClient)

    exit_code = await commands._run_probe(
        base_url="http://test",
        timeout=1.0,
        headers={},
        concurrency=1,
        specific_endpoints=[],
        output_format="json",
        fail_on_error=False,
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Probe failed" in captured.err


def test_run_watch_mode_one_iteration(monkeypatch):
    calls = []

    def fake_run(coro):
        calls.append("run")
        coro.close()
        return 0

    def fake_sleep(_):
        raise KeyboardInterrupt()

    monkeypatch.setattr(commands.asyncio, "run", fake_run)
    monkeypatch.setattr(commands.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        commands._run_watch_mode(
            base_url="http://test",
            timeout=1.0,
            headers={},
            concurrency=1,
            specific_endpoints=[],
            output_format="json",
            interval=1,
            fail_on_error=False,
        )
    assert calls == ["run"]
