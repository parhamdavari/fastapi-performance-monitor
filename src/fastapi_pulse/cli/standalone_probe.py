"""Standalone HTTP-based probe client for FastAPI Pulse CLI.

This module provides a standalone probe client that communicates with FastAPI
applications via HTTP, unlike the integrated PulseProbeManager which uses ASGI transport.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class EndpointProbeResult:
    """Result of probing a single endpoint."""

    endpoint_id: str
    method: str
    path: str
    status: str  # "healthy", "warning", "critical", "skipped"
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    checked_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "checked_at": self.checked_at,
        }


class StandaloneProbeClient:
    """HTTP-based probe client for health checking FastAPI endpoints."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        concurrency: int = 10,
        custom_headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize the standalone probe client.

        Args:
            base_url: Base URL of the FastAPI application (e.g., "http://localhost:8000")
            timeout: Request timeout in seconds
            concurrency: Maximum concurrent probe requests
            custom_headers: Optional headers to include in all requests (e.g., auth headers)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.custom_headers = custom_headers or {}

    async def fetch_endpoints(self) -> List[Dict[str, Any]]:
        """Fetch available endpoints from the Pulse API.

        Returns:
            List of endpoint metadata dictionaries

        Raises:
            httpx.HTTPError: If the request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/health/pulse/endpoints",
                headers=self.custom_headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("endpoints", [])

    async def probe_endpoints(
        self,
        endpoints: List[Dict[str, Any]],
    ) -> List[EndpointProbeResult]:
        """Probe multiple endpoints concurrently.

        Args:
            endpoints: List of endpoint metadata from the registry

        Returns:
            List of probe results
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            tasks = [
                self._probe_single_endpoint(client, endpoint)
                for endpoint in endpoints
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and return valid results
        return [r for r in results if isinstance(r, EndpointProbeResult)]

    async def _probe_single_endpoint(
        self,
        client: httpx.AsyncClient,
        endpoint_meta: Dict[str, Any],
    ) -> EndpointProbeResult:
        """Probe a single endpoint.

        Args:
            client: HTTP client instance
            endpoint_meta: Endpoint metadata including payload configuration

        Returns:
            Probe result for the endpoint
        """
        async with self.semaphore:
            endpoint_id = endpoint_meta["id"]
            method = endpoint_meta["method"]
            path = endpoint_meta["path"]

            # Get effective payload
            payload_info = endpoint_meta.get("payload", {})
            effective_payload = payload_info.get("effective")

            # Skip if no payload available
            if not effective_payload:
                return EndpointProbeResult(
                    endpoint_id=endpoint_id,
                    method=method,
                    path=path,
                    status="skipped",
                    checked_at=time.time(),
                )

            start = time.perf_counter()
            try:
                # Format path with parameters
                formatted_path = self._format_path(
                    path,
                    effective_payload.get("path_params", {}),
                )

                # Prepare headers
                headers = {
                    **self.custom_headers,
                    **(effective_payload.get("headers") or {}),
                    "x-pulse-probe": "true",
                }

                # Prepare request kwargs
                request_kwargs: Dict[str, Any] = {
                    "params": effective_payload.get("query") or None,
                    "headers": headers,
                }

                # Handle request body
                body = effective_payload.get("body")
                media_type = effective_payload.get("media_type") or "application/json"

                if body is not None:
                    if isinstance(body, (dict, list)) and media_type.startswith("application/json"):
                        request_kwargs["json"] = body
                    else:
                        if isinstance(body, (dict, list)):
                            request_kwargs["data"] = json.dumps(body)
                        else:
                            request_kwargs["data"] = body
                        request_kwargs.setdefault("headers", {})["content-type"] = media_type

                # Execute request
                response = await client.request(
                    method,
                    formatted_path,
                    **request_kwargs,
                )

                duration_ms = (time.perf_counter() - start) * 1000
                is_success = 200 <= response.status_code < 400

                # Determine health status
                if is_success and duration_ms <= 1000:
                    status = "healthy"
                elif is_success:
                    status = "warning"
                else:
                    status = "critical"

                return EndpointProbeResult(
                    endpoint_id=endpoint_id,
                    method=method,
                    path=path,
                    status=status,
                    status_code=response.status_code,
                    latency_ms=duration_ms,
                    error=response.text[:500] if not is_success else None,
                    checked_at=time.time(),
                )

            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                return EndpointProbeResult(
                    endpoint_id=endpoint_id,
                    method=method,
                    path=path,
                    status="critical",
                    status_code=None,
                    latency_ms=duration_ms,
                    error=str(exc),
                    checked_at=time.time(),
                )

    @staticmethod
    def _format_path(path: str, path_params: Dict[str, Any]) -> str:
        """Replace path parameters with actual values.

        Args:
            path: Path template (e.g., "/users/{id}")
            path_params: Parameter values

        Returns:
            Formatted path
        """
        formatted = path
        for key, value in (path_params or {}).items():
            formatted = formatted.replace(f"{{{key}}}", str(value))
        return formatted


__all__ = ["StandaloneProbeClient", "EndpointProbeResult"]
