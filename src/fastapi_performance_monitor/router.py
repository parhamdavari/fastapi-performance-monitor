"""
FastAPI router for exposing performance metrics.
"""

from fastapi import APIRouter
from .metrics import _metrics

router = APIRouter(prefix="/health", tags=["Performance Metrics"])

@router.get("/metrics", response_model_exclude_none=True)
def get_performance_metrics():
    """
    Endpoint to retrieve detailed performance metrics and SLA compliance.
    """
    # Get raw metrics from the collector
    performance_metrics = _metrics.get_metrics()
    
    # Calculate SLA compliance based on the summary
    summary = performance_metrics.get("summary", {})
    error_rate = summary.get("error_rate", 0)
    
    # SLA compliance can only be determined if we have enough data for P95
    if "p95_response_time" in summary:
        p95_response_time = summary["p95_response_time"]
        latency_sla_met = p95_response_time < 200
    else:
        p95_response_time = 0  # Default value when not available
        latency_sla_met = None # Not enough data to determine status

    error_rate_sla_met = error_rate < 5
    
    # Overall SLA depends on latency SLA being determined
    if latency_sla_met is None:
        overall_sla_met = None
    else:
        overall_sla_met = latency_sla_met and error_rate_sla_met

    # Structure the final response
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
            }
        },
    }
    
    return response_data
