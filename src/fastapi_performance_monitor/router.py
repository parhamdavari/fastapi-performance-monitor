"""Factory for FastAPI routers that expose performance metrics."""

from __future__ import annotations

from fastapi import APIRouter

from .metrics import PerformanceMetrics


def create_metrics_router(metrics: PerformanceMetrics) -> APIRouter:
    """Build a router that serves performance metrics derived from *metrics*."""

    router = APIRouter(prefix="/health", tags=["Performance Metrics"])

    @router.get("/metrics", response_model_exclude_none=True)
    def get_performance_metrics():
        performance_metrics = metrics.get_metrics()

        summary = performance_metrics.get("summary", {})
        error_rate = summary.get("error_rate", 0)

        if "p95_response_time" in summary:
            p95_response_time = summary["p95_response_time"]
            latency_sla_met = p95_response_time < 200
        else:
            p95_response_time = 0
            latency_sla_met = None

        error_rate_sla_met = error_rate < 5

        if latency_sla_met is None:
            overall_sla_met = None
        else:
            overall_sla_met = latency_sla_met and error_rate_sla_met

        response_data = {
            "performance_metrics": performance_metrics,
            "sla_compliance": {
                "latency_sla_met": latency_sla_met,
                "error_rate_sla_met": error_rate_sla_met,
                "overall_sla_met": overall_sla_met,
                "details": {
                    "p95_response_time": f"{p95_response_time:.2f}ms",
                    "p95_response_time_sla": "200ms",
                    "error_rate": f"{error_rate:.2f}%",
                    "error_rate_sla": "5%",
                },
            },
        }

        return response_data

    return router


__all__ = ["create_metrics_router"]
