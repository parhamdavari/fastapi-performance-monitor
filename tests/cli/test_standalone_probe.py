"""Unit tests for standalone probe client.

Note: These tests use ASGI transport to test the StandaloneProbeClient
without requiring a real HTTP server.
"""

import pytest
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from fastapi_pulse import add_pulse
from fastapi_pulse.cli.standalone_probe import StandaloneProbeClient, EndpointProbeResult


pytestmark = pytest.mark.asyncio


@pytest.fixture
def test_app():
    """Create a test FastAPI app with pulse monitoring."""
    app = FastAPI()
    add_pulse(app)

    @app.get("/test/success")
    async def success_endpoint():
        return {"message": "ok"}

    @app.get("/test/error")
    async def error_endpoint():
        raise RuntimeError("Test error")

    class Item(BaseModel):
        name: str
        quantity: int = 1

    @app.post("/test/items")
    async def create_item(item: Item):
        return item

    @app.get("/test/users/{user_id}")
    async def get_user(user_id: int):
        return {"user_id": user_id}

    return app


async def test_fetch_endpoints_with_asgi_transport(test_app):
    """Test fetching endpoints using ASGI transport."""
    # Use ASGI transport for testing without real HTTP server
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health/pulse/endpoints")
        assert response.status_code == 200
        data = response.json()

        endpoints = data.get("endpoints", [])
        assert len(endpoints) > 0

        endpoint_ids = {ep["id"] for ep in endpoints}
        assert "GET /test/success" in endpoint_ids
        assert "GET /test/error" in endpoint_ids
        assert "POST /test/items" in endpoint_ids


async def test_probe_result_dataclass():
    """Test EndpointProbeResult dataclass."""
    result = EndpointProbeResult(
        endpoint_id="GET /test",
        method="GET",
        path="/test",
        status="healthy",
        status_code=200,
        latency_ms=50.0,
    )

    assert result.endpoint_id == "GET /test"
    assert result.status == "healthy"

    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    assert result_dict["endpoint_id"] == "GET /test"
    assert result_dict["status_code"] == 200


async def test_path_formatting():
    """Test path parameter formatting."""
    from fastapi_pulse.cli.standalone_probe import StandaloneProbeClient

    formatted = StandaloneProbeClient._format_path(
        "/users/{user_id}/posts/{post_id}",
        {"user_id": 123, "post_id": 456}
    )

    assert formatted == "/users/123/posts/456"


async def test_endpoint_probing_with_asgi(test_app):
    """Test probing endpoints with ASGI transport."""
    # Prepare endpoint metadata (simulating what we'd get from the registry)
    endpoints_meta = [
        {
            "id": "GET /test/success",
            "method": "GET",
            "path": "/test/success",
            "payload": {
                "effective": {
                    "path_params": {},
                    "query": {},
                    "headers": {},
                    "body": None,
                    "media_type": None,
                }
            }
        }
    ]

    # Create client with ASGI transport
    client = StandaloneProbeClient(base_url="http://testserver")

    # Manually probe with ASGI transport
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as http_client:
        result = await client._probe_single_endpoint(http_client, endpoints_meta[0])

        assert result.endpoint_id == "GET /test/success"
        assert result.status in {"healthy", "warning"}
        assert result.status_code == 200
        assert result.latency_ms is not None


async def test_error_endpoint_probing(test_app):
    """Test probing an endpoint that raises an error."""
    endpoints_meta = [
        {
            "id": "GET /test/error",
            "method": "GET",
            "path": "/test/error",
            "payload": {
                "effective": {
                    "path_params": {},
                    "query": {},
                    "headers": {},
                    "body": None,
                    "media_type": None,
                }
            }
        }
    ]

    client = StandaloneProbeClient(base_url="http://testserver")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as http_client:
        result = await client._probe_single_endpoint(http_client, endpoints_meta[0])

        assert result.endpoint_id == "GET /test/error"
        assert result.status == "critical"
        assert result.status_code == 500


async def test_skipped_endpoint_without_payload(test_app):
    """Test that endpoints without effective payload are skipped."""
    endpoints_meta = [
        {
            "id": "POST /test/items",
            "method": "POST",
            "path": "/test/items",
            "payload": {
                "effective": None  # No payload available
            }
        }
    ]

    client = StandaloneProbeClient(base_url="http://testserver")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as http_client:
        result = await client._probe_single_endpoint(http_client, endpoints_meta[0])

        assert result.status == "skipped"


async def test_create_client_variants(test_app):
    client = StandaloneProbeClient(base_url="http://testserver")
    async with client._create_client() as http_client:
        assert str(http_client.base_url) == "http://testserver"

    client_with_asgi = StandaloneProbeClient(base_url="http://testserver", asgi_app=test_app)
    async with client_with_asgi._create_client() as http_client:
        response = await http_client.get("/health/pulse")
        assert response.status_code == 200
