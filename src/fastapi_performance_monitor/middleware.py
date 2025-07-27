"""
Performance Monitoring Middleware
================================
Middleware to collect performance metrics and monitor API health.
"""

import time
import logging
import re
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Import from within the package
from .metrics import _metrics

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect and monitor API performance metrics.
    """
    
    def __init__(self, app, enable_detailed_logging: bool = True):
        super().__init__(app)
        self.enable_detailed_logging = enable_detailed_logging
        self.metrics = _metrics
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect performance metrics."""
        start_time = time.time()
        
        correlation_id = request.headers.get("X-Correlation-ID", "unknown")
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        endpoint_path = self._normalize_path(request.url.path)
        
        # Skip recording metrics for performance dashboard routes
        if not endpoint_path.startswith('/performance'):
            self.metrics.record_request(
                endpoint=endpoint_path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
                correlation_id=correlation_id
            )
        
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        
        # Only log and check SLA for non-performance routes
        if not endpoint_path.startswith('/performance'):
            if self.enable_detailed_logging and (duration_ms > 1000 or response.status_code >= 400):
                self._log_performance_alert(request, endpoint_path, response.status_code, duration_ms, correlation_id)
            
            self._check_sla_violation(request, endpoint_path, correlation_id)
        
        return response
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics grouping."""
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path, flags=re.IGNORECASE)
        path = re.sub(r'/\d+', '/{id}', path)
        return path

    def _log_performance_alert(self, request: Request, path: str, status_code: int, duration_ms: float, correlation_id: str):
        log_level = logging.WARNING if duration_ms > 1000 else logging.ERROR
        logger.log(
            log_level,
            f"Performance alert: {request.method} {path}",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "alert_type": "slow_request" if duration_ms > 1000 else "error_response"
            }
        )

    def _check_sla_violation(self, request: Request, endpoint_path: str, correlation_id: str):
        current_metrics = self.metrics.get_metrics()
        endpoint_key = f"{request.method} {endpoint_path}"
        
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
