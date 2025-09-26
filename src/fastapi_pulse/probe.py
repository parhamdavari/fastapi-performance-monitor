"""Active probing utilities for Pulse."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from .metrics import PulseMetrics
from .registry import EndpointInfo


ProbeResultStatus = str


@dataclass
class ProbeResult:
    endpoint_id: str
    method: str
    path: str
    status: ProbeResultStatus
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


@dataclass
class ProbeJob:
    job_id: str
    status: str = "queued"
    total_targets: int = 0
    completed: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    results: Dict[str, ProbeResult] = field(default_factory=dict)
    _future: asyncio.Future | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total": self.total_targets,
            "completed": self.completed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "results": {key: result.to_dict() for key, result in self.results.items()},
        }


class PulseProbeManager:
    """Runs active health probes against the FastAPI application."""

    def __init__(
        self,
        app,
        metrics: PulseMetrics,
        *,
        concurrency: int = 10,
        request_timeout: float = 10.0,
    ) -> None:
        self.app = app
        self.metrics = metrics
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.request_timeout = request_timeout
        self._jobs: Dict[str, ProbeJob] = {}
        self._last_job_id: Optional[str] = None

    def start_probe(self, endpoints: List[EndpointInfo]) -> str:
        """Start a probe job for the provided endpoints and return its identifier."""
        loop = asyncio.get_running_loop()
        job_id = uuid.uuid4().hex
        job = ProbeJob(job_id=job_id)
        job.total_targets = len(endpoints)
        job._future = loop.create_future()
        job.results = {
            endpoint.id: ProbeResult(
                endpoint_id=endpoint.id,
                method=endpoint.method,
                path=endpoint.path,
                status="queued",
            )
            for endpoint in endpoints
        }
        self._jobs[job_id] = job
        self._last_job_id = job_id

        loop.create_task(self._run_job(job, endpoints))
        return job_id

    async def wait_for_completion(self, job_id: str) -> ProbeJob:
        """Await job completion (useful for tests)."""
        job = self._jobs.get(job_id)
        if job is None or job._future is None:
            raise KeyError(f"Unknown probe job: {job_id}")
        await job._future
        return job

    def get_job(self, job_id: str) -> Optional[ProbeJob]:
        return self._jobs.get(job_id)

    def last_job(self) -> Optional[ProbeJob]:
        if self._last_job_id:
            return self._jobs.get(self._last_job_id)
        return None

    async def _run_job(self, job: ProbeJob, endpoints: List[EndpointInfo]) -> None:
        job.status = "running"
        job.started_at = time.time()

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://pulse-probe") as client:
            tasks = [
                self._probe_endpoint(job, client, endpoint)
                for endpoint in endpoints
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        job.status = "completed"
        job.completed_at = time.time()
        if job._future and not job._future.done():
            job._future.set_result(job)

    async def _probe_endpoint(
        self,
        job: ProbeJob,
        client: httpx.AsyncClient,
        endpoint: EndpointInfo,
    ) -> None:
        async with self.semaphore:
            result = job.results[endpoint.id]

            # Skip endpoints that require additional input.
            if endpoint.requires_input:
                result.status = "skipped"
                result.checked_at = time.time()
                job.completed += 1
                return

            start = time.perf_counter()
            try:
                response = await client.request(
                    endpoint.method,
                    endpoint.path,
                    timeout=self.request_timeout,
                    headers={"x-pulse-probe": "true"},
                )
                duration_ms = (time.perf_counter() - start) * 1000
                result.status_code = response.status_code
                result.latency_ms = duration_ms
                result.checked_at = time.time()

                is_success = 200 <= response.status_code < 400
                if is_success and duration_ms <= 1000:
                    result.status = "healthy"
                elif is_success:
                    result.status = "warning"
                else:
                    result.status = "critical"
                    result.error = response.text[:500]

                self.metrics.record_request(
                    endpoint=endpoint.path,
                    method=endpoint.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    correlation_id="pulse-probe",
                )

            except Exception as exc:  # pragma: no cover - network issues
                duration_ms = (time.perf_counter() - start) * 1000
                result.status = "critical"
                result.error = str(exc)
                result.status_code = None
                result.latency_ms = duration_ms
                result.checked_at = time.time()

                self.metrics.record_request(
                    endpoint=endpoint.path,
                    method=endpoint.method,
                    status_code=599,  # Non-standard to indicate probe failure
                    duration_ms=duration_ms,
                    correlation_id="pulse-probe",
                )

            finally:
                job.completed += 1

