"""
Integration tests for the FastAPI Performance Monitor.

These tests ensure that the middleware, router, and metrics collector
work together correctly within a real FastAPI application.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_performance_monitor import (
    METRICS_STATE_KEY,
    add_performance_monitor,
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
    add_performance_monitor(app)

    @app.get("/test/success")
    async def success_endpoint():
        return {"message": "ok"}

    @app.get("/test/error")
    async def error_endpoint():
        raise RuntimeError("This is a test error")

    return app

@pytest.fixture(scope="function")
def client(test_app):
    """Fixture to create a TestClient for the test app."""
    with TestClient(test_app) as c:
        yield c

async def test_middleware_and_router_integration(client: TestClient):
    """
    Verify the end-to-end loop: a request is made, the middleware records it,
    and the /health/metrics endpoint reports it.
    """
    # Make a request to a dummy endpoint
    response = client.get("/test/success")
    assert response.status_code == 200
    assert "x-response-time-ms" in response.headers

    # Now, check the metrics endpoint
    metrics_response = client.get("/health/metrics")
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

    metrics_response = client.get("/health/metrics")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is None
    assert data["sla_compliance"]["overall_sla_met"] is None

async def test_sla_fail_state(client: TestClient):
    """Verify that when P95 exceeds the threshold, the SLA status is false."""
    # Generate 20 requests with a high response time
    app = client.app
    metrics = getattr(app.state, METRICS_STATE_KEY)
    for i in range(20):
        # Manually record a slow request
        metrics.record_request(
            endpoint="/test/slow", method="GET", status_code=200, duration_ms=300.0 + i
        )

    metrics_response = client.get("/health/metrics")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is False
    assert data["sla_compliance"]["overall_sla_met"] is False

async def test_sla_pass_state(client: TestClient):
    """Verify that when P95 is within the threshold, the SLA status is true."""
    # Generate 20 requests with a fast response time
    app = client.app
    metrics = getattr(app.state, METRICS_STATE_KEY)
    for i in range(20):
        metrics.record_request(
            endpoint="/test/fast", method="GET", status_code=200, duration_ms=50.0 + i
        )

    metrics_response = client.get("/health/metrics")
    data = metrics_response.json()

    assert data["sla_compliance"]["latency_sla_met"] is True
    assert data["sla_compliance"]["overall_sla_met"] is True
