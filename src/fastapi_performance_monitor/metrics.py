"""
Thread-safe performance metrics collector.
"""

import threading
from collections import defaultdict, deque
from typing import Dict, Any

class PerformanceMetrics:
    """Thread-safe performance metrics collector."""
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._lock = threading.Lock()
        
        # Metrics storage
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.response_times = defaultdict(lambda: deque(maxlen=max_samples))
        self.status_codes = defaultdict(lambda: defaultdict(int))
        
        # Business metrics
        self.endpoint_metrics = defaultdict(lambda: {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_response_time": 0.0,
            "p95_response_time": 0.0,
            "p99_response_time": 0.0
        })
    
    def _calculate_percentile(self, data, percentile):
        """Calculates the given percentile using linear interpolation."""
        size = len(data)
        if size == 0:
            return 0.0
        
        # Ensure data is sorted
        sorted_data = sorted(data)
        
        # Calculate the rank/index
        k = (size - 1) * (percentile / 100.0)
        f = int(k) # floor
        c = k - f  # fractional part
        
        if f == size - 1:
            return sorted_data[f]
        
        return sorted_data[f] + (sorted_data[f + 1] - sorted_data[f]) * c

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
            
            # Response times
            self.response_times[key].append(duration_ms)
            
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
            times = list(self.response_times[key])
            if times:
                metrics["avg_response_time"] = sum(times) / len(times)
                
                if len(times) >= 2: # Percentiles need at least 2 points to interpolate
                    metrics["p95_response_time"] = self._calculate_percentile(times, 95)
                    metrics["p99_response_time"] = self._calculate_percentile(times, 99)

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
        
        all_times = []
        for times in self.response_times.values():
            all_times.extend(times)
        
        summary = {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0,
            "avg_response_time": sum(all_times) / len(all_times) if all_times else 0,
        }
        
        if len(all_times) >= 2: # Percentiles need at least 2 points to interpolate
            summary["p95_response_time"] = self._calculate_percentile(all_times, 95)
            summary["p99_response_time"] = self._calculate_percentile(all_times, 99)
        
        return summary

# Global metrics instance
_metrics = PerformanceMetrics()
