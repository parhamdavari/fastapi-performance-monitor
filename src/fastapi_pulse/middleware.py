"""ASGI middleware to collect pulse metrics and monitor API health."""

from __future__ import annotations

import time
import logging
import re
from typing import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import Message, Receive, Scope, Send

from .metrics import PulseMetrics

logger = logging.getLogger(__name__)

SLOW_REQUEST_THRESHOLD_MS = 1000
SLA_LATENCY_THRESHOLD_MS = 200
DEFAULT_ERROR_BODY = b'{"detail":"Internal Server Error"}'


class PulseMiddleware:
    """ASGI middleware that records latency, status codes, and SLA metrics."""

    def __init__(
        self,
        app: Callable,
        *,
        metrics: PulseMetrics,
        enable_detailed_logging: bool = True,
    ):
        self.app = app
        self.enable_detailed_logging = enable_detailed_logging
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI calls and record metrics for HTTP requests."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        correlation_id = headers.get("x-correlation-id", "unknown")
        method = scope.get("method", "GET")
        raw_path = scope.get("path", "/")
        endpoint_path = self._normalize_path(raw_path)
        track_metrics = not endpoint_path.startswith("/performance")

        start_time = time.perf_counter()
        status_code = 500
        duration_ms: float | None = None
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, duration_ms, response_started

            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]

                # Ensure we can mutate headers and attach latency information.
                raw_headers = message.setdefault("headers", [])
                headers_obj = MutableHeaders(raw=raw_headers)
                duration_ms = self._ensure_duration(duration_ms, start_time)
                headers_obj["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

            elif message["type"] == "http.response.body":
                duration_ms = self._ensure_duration(duration_ms, start_time)

            await send(message)

        request_failed = False

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            request_failed = True
            logger.exception(
                "Unhandled exception while processing request",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": endpoint_path,
                },
            )

            duration_ms = self._ensure_duration(duration_ms, start_time)

            if not response_started:
                status_code = 500
                await self._emit_fallback_response(send, duration_ms)
            else:
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                )
        finally:
            duration_ms = self._ensure_duration(duration_ms, start_time)
            final_status = status_code if not request_failed else 500

            if track_metrics:
                self.metrics.record_request(
                    endpoint=endpoint_path,
                    method=method,
                    status_code=final_status,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id,
                )

                if self.enable_detailed_logging and (
                    duration_ms > SLOW_REQUEST_THRESHOLD_MS or final_status >= 400
                ):
                    self._log_performance_alert(
                        method=method,
                        path=endpoint_path,
                        status_code=final_status,
                        duration_ms=duration_ms,
                        correlation_id=correlation_id,
                    )

                self._check_sla_violation(
                    method=method,
                    endpoint_path=endpoint_path,
                    correlation_id=correlation_id,
                )
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics grouping."""
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path, flags=re.IGNORECASE)
        path = re.sub(r'/\d+', '/{id}', path)
        return path

    def _log_performance_alert(self, method: str, path: str, status_code: int, duration_ms: float, correlation_id: str) -> None:
        log_level = (
            logging.WARNING if duration_ms > SLOW_REQUEST_THRESHOLD_MS else logging.ERROR
        )
        logger.log(
            log_level,
            f"Performance alert: {method} {path}",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "alert_type": (
                    "slow_request"
                    if duration_ms > SLOW_REQUEST_THRESHOLD_MS
                    else "error_response"
                )
            }
        )

    def _check_sla_violation(self, method: str, endpoint_path: str, correlation_id: str) -> None:
        current_metrics = self.metrics.get_metrics()
        endpoint_key = f"{method} {endpoint_path}"
        
        if endpoint_key in current_metrics["endpoint_metrics"]:
            endpoint_stats = current_metrics["endpoint_metrics"][endpoint_key]
            p95_time = endpoint_stats.get("p95_response_time", 0)
            
            if p95_time > SLA_LATENCY_THRESHOLD_MS:  # SLA violation
                logger.warning(
                    "SLA violation detected",
                    extra={
                        "correlation_id": correlation_id,
                        "endpoint": endpoint_key,
                        "p95_response_time": p95_time,
                        "sla_limit": SLA_LATENCY_THRESHOLD_MS,
                        "violation_type": "latency_sla"
                    }
                )

    def _ensure_duration(self, cached_duration: float | None, start_time: float) -> float:
        """Return the cached duration if present, otherwise compute it."""
        if cached_duration is not None:
            return cached_duration
        return (time.perf_counter() - start_time) * 1000

    async def _emit_fallback_response(self, send: Send, duration_ms: float) -> None:
        """Send a JSON 500 response when the downstream app fails early."""
        headers_list: list[tuple[bytes, bytes]] = []
        headers_obj = MutableHeaders(raw=headers_list)
        headers_obj["content-type"] = "application/json"
        headers_obj["content-length"] = str(len(DEFAULT_ERROR_BODY))
        headers_obj["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": headers_list,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": DEFAULT_ERROR_BODY,
                "more_body": False,
            }
        )
