"""
Integration tests for FastAPI Pulse.

These tests ensure that the middleware, router, metrics collector,
and probe manager work together correctly within a real FastAPI application.
"""

import asyncio
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_pulse import (
    PULSE_STATE_KEY,
    PulseMetrics,
    add_pulse,
)

# Pytest-asyncio marker
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def test_app():
    """
    Fixture to create a fresh FastAPI app with the monitor for each test function.
    Using 'function' scope ensures strict test isolation.
    """
    app = FastAPI()
    add_pulse(app)

    @app.get("/test/success")
    async def success_endpoint():
        return {"message": "ok"}

    @app.get("/test/error")
    async def error_endpoint():
        raise RuntimeError("This is a test error")

    class Widget(BaseModel):
        name: str
        quantity: int = 1

    @app.post("/test/widget", response_model=Widget)
    async def create_widget(widget: Widget):
        return widget

    return app

@pytest.fixture(scope="function")
def client(test_app):
    """Fixture to create a TestClient for the test app."""
    with TestClient(test_app) as c:
        yield c

async def test_middleware_and_router_integration(client: TestClient):
    """
    Verify the end-to-end loop: a request is made, the middleware records it,
    and the /health/pulse endpoint reports it.
    """
    # Make a request to a dummy endpoint
    response = client.get("/test/success")
    assert response.status_code == 200
    assert "x-response-time-ms" in response.headers

    # Now, check the metrics endpoint
    metrics_response = client.get("/health/pulse")
    assert metrics_response.status_code == 200
    data = metrics_response.json()

    # Verify that the request was recorded
    endpoint_metrics = data["performance_metrics"]["endpoint_metrics"]
    assert "GET /test/success" in endpoint_metrics
    assert endpoint_metrics["GET /test/success"]["total_requests"] == 1
    assert endpoint_metrics["GET /test/success"]["success_count"] == 1

# --- SLA Status Logic Tests ---

async def test_sla_initial_state_is_null(client: TestClient):
    """Verify that with insufficient data, the SLA status is null."""
    # With a fresh app, make one request (not enough for P95)
    client.get("/test/success")

    metrics_response = client.get("/health/pulse")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is None
    assert data["sla_compliance"]["overall_sla_met"] is None

async def test_sla_fail_state(client: TestClient):
    """Verify that when P95 exceeds the threshold, the SLA status is false."""
    # Generate 20 requests with a high response time
    app = client.app
    metrics = getattr(app.state, PULSE_STATE_KEY)
    for i in range(20):
        # Manually record a slow request
        metrics.record_request(
            endpoint="/test/slow", method="GET", status_code=200, duration_ms=300.0 + i
        )

    metrics_response = client.get("/health/pulse")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is False
    assert data["sla_compliance"]["overall_sla_met"] is False

async def test_sla_pass_state(client: TestClient):
    """Verify that when P95 is within the threshold, the SLA status is true."""
    # Generate 20 requests with a fast response time
    app = client.app
    metrics = getattr(app.state, PULSE_STATE_KEY)
    for i in range(20):
        metrics.record_request(
            endpoint="/test/fast", method="GET", status_code=200, duration_ms=50.0 + i
        )

    metrics_response = client.get("/health/pulse")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is True
    assert data["sla_compliance"]["overall_sla_met"] is True


async def test_exception_is_translated_to_500_response(client: TestClient):
    """Unhandled exceptions should return JSON 500 responses and emit metrics."""
    response = client.get("/test/error")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "x-response-time-ms" in response.headers

    metrics_response = client.get("/health/pulse")
    data = metrics_response.json()["performance_metrics"]["endpoint_metrics"]

    error_stats = data["GET /test/error"]
    assert error_stats["total_requests"] == 1
    assert error_stats["error_count"] == 1


def test_add_pulse_rejects_conflicting_metrics():
    app = FastAPI()
    with pytest.raises(ValueError):
        add_pulse(app, metrics=PulseMetrics(), metrics_factory=lambda: PulseMetrics())


async def test_endpoint_registry_and_probe_flow(client: TestClient):
    """Registry endpoint should list routes and probe API should execute them."""
    # Registry should expose the test routes.
    response = client.get("/health/pulse/endpoints")
    assert response.status_code == 200
    registry_payload = response.json()
    endpoint_ids = {entry["id"] for entry in registry_payload["endpoints"]}
    assert "GET /test/success" in endpoint_ids
    assert "GET /test/error" in endpoint_ids
    assert "POST /test/widget" in endpoint_ids

    # Trigger a probe job for all endpoints.
    start_response = client.post("/health/pulse/probe")
    assert start_response.status_code == 200
    job_info = start_response.json()
    job_id = job_info["job_id"]

    # Poll for completion.
    status = None
    for _ in range(30):
        await asyncio.sleep(0.1)
        status_response = client.get(f"/health/pulse/probe/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["status"] == "completed":
            break
    assert status is not None
    assert status["status"] == "completed"

    # Endpoints API should now include last probe data.
    refreshed = client.get("/health/pulse/endpoints").json()
    statuses = {row["id"]: row["last_probe"]["status"] for row in refreshed["endpoints"]}
    assert statuses["GET /test/success"] in {"healthy", "warning"}
    assert statuses["GET /test/error"] == "critical"

    widget_row = next(item for item in refreshed["endpoints"] if item["id"] == "POST /test/widget")
    assert widget_row["payload"]["source"] in {"generated", "custom"}

    # Save a custom payload for the widget endpoint and run a probe using it.
    endpoint_id = "POST /test/widget"
    custom_payload = {
        "path_params": {},
        "query": {"refresh": "true"},
        "headers": {"x-api-key": "secret"},
        "body": {"name": "custom", "quantity": 5},
    }
    encoded_id = quote(endpoint_id, safe='')
    save_response = client.put(f"/health/pulse/probe/{encoded_id}/payload", json=custom_payload)
    assert save_response.status_code == 200
    assert save_response.json()["payload"]["source"] == "custom"

    custom_job = client.post("/health/pulse/probe", json={"endpoints": [endpoint_id]}).json()
    job_id = custom_job["job_id"]
    for _ in range(30):
        await asyncio.sleep(0.1)
        status_response = client.get(f"/health/pulse/probe/{job_id}")
        status = status_response.json()
        if status["status"] == "completed":
            break
    refreshed = client.get("/health/pulse/endpoints").json()
    widget_row = next(item for item in refreshed["endpoints"] if item["id"] == endpoint_id)
    assert widget_row["payload"]["source"] == "custom"
    assert widget_row["payload"]["effective"]["headers"]["x-api-key"] == "secret"

    # Reset payload back to generated and verify.
    reset_response = client.delete(f"/health/pulse/probe/{encoded_id}/payload")
    assert reset_response.status_code == 200
    refreshed = client.get("/health/pulse/endpoints").json()
    widget_row = next(item for item in refreshed["endpoints"] if item["id"] == endpoint_id)
    assert widget_row["payload"]["source"] == "generated"
