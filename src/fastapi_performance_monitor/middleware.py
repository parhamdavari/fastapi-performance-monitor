"""ASGI middleware to collect performance metrics and monitor API health."""

import time
import logging
import re
from typing import Callable

from starlette.datastructures import Headers, MutableHeaders

# Import from within the package
from .metrics import _metrics

logger = logging.getLogger(__name__)


class PerformanceMiddleware:
    """ASGI middleware that records latency, status codes, and SLA metrics."""

    def __init__(self, app: Callable, enable_detailed_logging: bool = True):
        self.app = app
        self.enable_detailed_logging = enable_detailed_logging
        self.metrics = _metrics

    async def __call__(self, scope, receive, send):
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
        async def send_wrapper(message):
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

                # Ensure we can mutate headers and attach latency information.
                raw_headers = message.setdefault("headers", [])
                headers_obj = MutableHeaders(raw=raw_headers)
                duration_ms = (time.perf_counter() - start_time) * 1000
                headers_obj["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

            await send(message)

        request_failed = False

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            request_failed = True
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
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
                    duration_ms > 1000 or final_status >= 400
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

    def _log_performance_alert(self, method: str, path: str, status_code: int, duration_ms: float, correlation_id: str):
        log_level = logging.WARNING if duration_ms > 1000 else logging.ERROR
        logger.log(
            log_level,
            f"Performance alert: {method} {path}",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "alert_type": "slow_request" if duration_ms > 1000 else "error_response"
            }
        )

    def _check_sla_violation(self, method: str, endpoint_path: str, correlation_id: str):
        current_metrics = self.metrics.get_metrics()
        endpoint_key = f"{method} {endpoint_path}"
        
        if endpoint_key in current_metrics["endpoint_metrics"]:
            endpoint_stats = current_metrics["endpoint_metrics"][endpoint_key]
            p95_time = endpoint_stats.get("p95_response_time", 0)
            
            if p95_time > 200:  # SLA violation
                logger.warning(
                    "SLA violation detected",
                    extra={
                        "correlation_id": correlation_id,
                        "endpoint": endpoint_key,
                        "p95_response_time": p95_time,
                        "sla_limit": 200,
                        "violation_type": "latency_sla"
                    }
                )
