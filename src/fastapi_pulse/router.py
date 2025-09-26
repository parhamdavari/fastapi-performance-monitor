"""Factory for FastAPI routers that expose pulse metrics."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .constants import (
    PULSE_ENDPOINT_REGISTRY_KEY,
    PULSE_PAYLOAD_STORE_KEY,
    PULSE_PROBE_MANAGER_KEY,
)
from .metrics import PulseMetrics
from .payload_store import PulsePayloadStore
from .probe import PulseProbeManager
from .registry import EndpointInfo, PulseEndpointRegistry
from .sample_builder import SamplePayloadBuilder


class ProbeRequest(BaseModel):
    endpoints: Optional[List[str]] = None


class PayloadUpdate(BaseModel):
    path_params: Dict[str, Any] = {}
    query: Dict[str, Any] = {}
    headers: Dict[str, Any] = {}
    body: Optional[Any] = None
    media_type: Optional[str] = None


def _get_registry(request: Request) -> PulseEndpointRegistry:
    registry = getattr(request.app.state, PULSE_ENDPOINT_REGISTRY_KEY, None)
    if registry is None:
        raise RuntimeError("Pulse endpoint registry is not initialized. Did you call add_pulse()?")
    return registry


def _get_probe_manager(request: Request) -> PulseProbeManager:
    manager = getattr(request.app.state, PULSE_PROBE_MANAGER_KEY, None)
    if manager is None:
        raise RuntimeError("Pulse probe manager is not initialized. Did you call add_pulse()?")
    return manager


def _get_payload_store(request: Request) -> PulsePayloadStore:
    store = getattr(request.app.state, PULSE_PAYLOAD_STORE_KEY, None)
    if store is None:
        raise RuntimeError("Pulse payload store is not initialized. Did you call add_pulse()?")
    return store


def _serialize_probe_result(result) -> Dict[str, Any]:
    if result is None:
        return {
            "status": "unknown",
            "status_code": None,
            "latency_ms": None,
            "error": None,
            "checked_at": None,
            "checked_at_iso": None,
            "payload": None,
        }

    checked_at_iso = None
    if result.checked_at is not None:
        checked_at_iso = datetime.fromtimestamp(result.checked_at, tz=timezone.utc).isoformat()

    return {
        "status": result.status,
        "status_code": result.status_code,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "checked_at": result.checked_at,
        "checked_at_iso": checked_at_iso,
        "payload": result.payload,
    }


def _serialize_endpoint(
    endpoint: EndpointInfo,
    endpoint_metrics: Dict[str, Any],
    probe_result,
    payload_info: Dict[str, Any],
) -> Dict[str, Any]:
    metrics_snapshot = endpoint_metrics.get(endpoint.id, {})
    total_requests = metrics_snapshot.get("total_requests", 0)
    error_count = metrics_snapshot.get("error_count", 0)
    error_rate = (
        (error_count / total_requests) * 100
        if total_requests else 0
    )
    return {
        "id": endpoint.id,
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
        "tags": endpoint.tags,
        "requires_input": endpoint.requires_input,
        "metrics": {
            "total_requests": total_requests,
            "success_count": metrics_snapshot.get("success_count", 0),
            "error_count": error_count,
            "avg_response_time": metrics_snapshot.get("avg_response_time"),
            "p95_response_time": metrics_snapshot.get("p95_response_time"),
            "error_rate": error_rate,
        },
        "last_probe": _serialize_probe_result(probe_result),
        "payload": payload_info,
    }


def create_pulse_router(metrics: PulseMetrics) -> APIRouter:
    """Build a router that serves pulse metrics derived from *metrics*."""

    router = APIRouter(prefix="/health", tags=["Pulse Metrics"])

    @router.get("/pulse", response_model_exclude_none=True)
    def get_pulse_metrics():
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

    @router.get("/pulse/endpoints")
    def list_endpoints(request: Request):
        registry = _get_registry(request)
        manager = _get_probe_manager(request)
        payload_store = _get_payload_store(request)
        builder = SamplePayloadBuilder(registry.openapi_schema)

        endpoints = registry.list_endpoints()
        metrics_snapshot = metrics.get_metrics().get("endpoint_metrics", {})
        last_job = manager.last_job()
        probe_results = last_job.results if last_job else {}
        payload_entries = []
        auto_count = 0
        requires_input_count = 0

        for endpoint in endpoints:
            custom_payload = payload_store.get(endpoint.id)
            generated_payload = builder.build(endpoint)
            effective_payload = None
            source = "none"
            if custom_payload:
                effective_payload = deepcopy(custom_payload)
                source = "custom"
            elif generated_payload:
                effective_payload = deepcopy(generated_payload)
                source = "generated"

            can_probe = effective_payload is not None
            if can_probe:
                auto_count += 1
                effective_payload["source"] = source
            else:
                requires_input_count += 1

            payload_info = {
                "source": source,
                "custom": custom_payload,
                "generated": generated_payload,
                "effective": effective_payload,
            }

            payload_entries.append(
                _serialize_endpoint(
                    endpoint,
                    metrics_snapshot,
                    probe_results.get(endpoint.id),
                    payload_info,
                )
            )

        response: Dict[str, Any] = {
            "endpoints": payload_entries,
            "summary": {
                "total": len(endpoints),
                "auto_probed": auto_count,
                "requires_input": requires_input_count,
            },
        }

        if last_job:
            response["summary"].update(
                {
                    "last_job_id": last_job.job_id,
                    "last_job_status": last_job.status,
                    "last_job_started_at": last_job.started_at,
                    "last_job_completed_at": last_job.completed_at,
                }
            )

        return response

    @router.post("/pulse/probe")
    async def trigger_probe(request: Request, payload: ProbeRequest | None = None):
        registry = _get_registry(request)
        manager = _get_probe_manager(request)

        endpoint_map = registry.get_endpoint_map()

        if payload and payload.endpoints:
            missing = [endpoint_id for endpoint_id in payload.endpoints if endpoint_id not in endpoint_map]
            if missing:
                raise HTTPException(status_code=404, detail={"missing_endpoints": missing})
            targets = [endpoint_map[endpoint_id] for endpoint_id in payload.endpoints]
        else:
            targets = registry.list_endpoints()

        job_id = manager.start_probe(targets)
        job = manager.get_job(job_id)
        return {"job_id": job_id, "total": job.total_targets if job else len(targets)}

    @router.get("/pulse/probe/{job_id}")
    def probe_status(request: Request, job_id: str):
        manager = _get_probe_manager(request)
        job = manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Probe job not found")
        return job.to_dict()

    @router.put("/pulse/probe/{endpoint_id:path}/payload")
    def save_payload(request: Request, endpoint_id: str, update: PayloadUpdate):
        registry = _get_registry(request)
        payload_store = _get_payload_store(request)
        endpoint_map = registry.get_endpoint_map()
        if endpoint_id not in endpoint_map:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        stored = payload_store.set(endpoint_id, update.model_dump())
        stored["source"] = "custom"
        return {"status": "ok", "payload": stored}

    @router.delete("/pulse/probe/{endpoint_id:path}/payload")
    def delete_payload(request: Request, endpoint_id: str):
        registry = _get_registry(request)
        payload_store = _get_payload_store(request)
        endpoint_map = registry.get_endpoint_map()
        if endpoint_id not in endpoint_map:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        payload_store.delete(endpoint_id)
        return {"status": "ok"}

    return router


__all__ = ["create_pulse_router"]
