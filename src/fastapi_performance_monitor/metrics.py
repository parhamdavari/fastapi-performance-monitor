"""Thread-safe performance metrics collector with rolling quantile tracking."""

from __future__ import annotations

import threading
import time
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Any, Deque

from tdigest import TDigest


@dataclass
class _DigestBucket:
    """Container for digest data within a fixed time bucket."""

    start: float
    digest: TDigest
    count: int = 0
    total: float = 0.0


class RollingWindowDigest:
    """Maintain TDigest statistics over a sliding time window."""

    def __init__(
        self,
        window_seconds: int = 300,
        bucket_seconds: int = 60,
        delta: float = 0.01,
        K: int = 25,
    ) -> None:
        self.window_seconds = window_seconds
        self.bucket_seconds = max(1, bucket_seconds)
        self.delta = delta
        self.K = K
        self._buckets: Deque[_DigestBucket] = deque()

    def add(self, value: float, timestamp: float | None = None) -> None:
        """Add a latency sample into the rolling window."""
        now = time.time() if timestamp is None else timestamp
        self._trim(now)

        bucket_start = math.floor(now / self.bucket_seconds) * self.bucket_seconds

        if self._buckets and self._buckets[-1].start == bucket_start:
            bucket = self._buckets[-1]
        else:
            bucket = _DigestBucket(
                start=bucket_start,
                digest=TDigest(delta=self.delta, K=self.K),
            )
            self._buckets.append(bucket)

        bucket.digest.update(value)
        bucket.count += 1
        bucket.total += value

    def count(self) -> int:
        self._refresh()
        return sum(bucket.count for bucket in self._buckets)

    def total(self) -> float:
        self._refresh()
        return sum(bucket.total for bucket in self._buckets)

    def mean(self) -> float:
        self._refresh()
        total = 0.0
        count = 0
        for bucket in self._buckets:
            total += bucket.total
            count += bucket.count
        if count == 0:
            return 0.0
        return total / count

    def percentile(self, percentile: float) -> float | None:
        """Return the requested percentile (0-100) if enough data exists."""
        self._refresh()
        merged = TDigest(delta=self.delta, K=self.K)
        total_count = 0
        for bucket in self._buckets:
            merged = merged + bucket.digest
            total_count += bucket.count

        if total_count < 2:
            return None

        if merged.n < 2:
            return None

        merged.compress()
        return float(merged.percentile(percentile))

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._buckets and self._buckets[0].start < cutoff:
            self._buckets.popleft()

    def _refresh(self) -> None:
        self._trim(time.time())


class PerformanceMetrics:
    """Thread-safe performance metrics collector."""

    def __init__(
        self,
        max_samples: int = 1000,
        window_seconds: int = 300,
        bucket_seconds: int = 60,
    ):
        # max_samples is kept for backwards compatibility but superseded by the
        # rolling window configuration.
        self.max_samples = max_samples
        self._lock = threading.Lock()

        self.window_seconds = window_seconds
        self.bucket_seconds = bucket_seconds

        self._latency_trackers = defaultdict(
            lambda: RollingWindowDigest(
                window_seconds=self.window_seconds,
                bucket_seconds=self.bucket_seconds,
            )
        )
        self._global_latency = RollingWindowDigest(
            window_seconds=self.window_seconds,
            bucket_seconds=self.bucket_seconds,
        )

        # Metrics storage
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.status_codes = defaultdict(lambda: defaultdict(int))

        # Business metrics
        self.endpoint_metrics = defaultdict(
            lambda: {
                "total_requests": 0,
                "success_count": 0,
                "error_count": 0,
                "avg_response_time": 0.0,
                "p95_response_time": 0.0,
                "p99_response_time": 0.0,
                "window_seconds": self.window_seconds,
            }
        )
    def record_request(self, 
                      endpoint: str, 
                      method: str, 
                      status_code: int, 
                      duration_ms: float,
                      correlation_id: str = None):
        """Record a request's performance metrics."""
        with self._lock:
            key = f"{method} {endpoint}"
            
            # Basic counters
            self.request_counts[key] += 1
            self.status_codes[key][status_code] += 1
            
            # Latency tracking
            tracker = self._latency_trackers[key]
            tracker.add(duration_ms)
            self._global_latency.add(duration_ms)
            
            # Error tracking
            if status_code >= 400:
                self.error_counts[key] += 1
            
            # Update endpoint metrics
            metrics = self.endpoint_metrics[key]
            metrics["total_requests"] += 1
            
            if status_code < 400:
                metrics["success_count"] += 1
            else:
                metrics["error_count"] += 1
            
            # Calculate stats
            metrics["avg_response_time"] = tracker.mean()

            p95 = tracker.percentile(95)
            p99 = tracker.percentile(99)

            if p95 is not None:
                metrics["p95_response_time"] = p95
            if p99 is not None:
                metrics["p99_response_time"] = p99

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        with self._lock:
            return {
                "request_counts": dict(self.request_counts),
                "error_counts": dict(self.error_counts),
                "endpoint_metrics": dict(self.endpoint_metrics),
                "summary": self._calculate_summary()
            }
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate summary metrics across all endpoints."""
        total_requests = sum(self.request_counts.values())
        total_errors = sum(self.error_counts.values())

        avg_latency = self._global_latency.mean()
        p95 = self._global_latency.percentile(95)
        p99 = self._global_latency.percentile(99)

        summary = {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0,
            "avg_response_time": avg_latency,
            "window_seconds": self.window_seconds,
        }

        if p95 is not None:
            summary["p95_response_time"] = p95
        if p99 is not None:
            summary["p99_response_time"] = p99

        return summary
