"""
FastAPI Performance Monitor
===========================

A plug-and-play performance monitoring tool for FastAPI applications,
providing real-time metrics and a dashboard.
"""

__version__ = "0.1.3"

import importlib.resources
from typing import Callable, Optional

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .metrics import PerformanceMetrics
from .middleware import PerformanceMiddleware
from .router import create_metrics_router


METRICS_STATE_KEY = "fastapi_performance_monitor_metrics"

def add_performance_monitor(
    app: FastAPI, 
    enable_detailed_logging: bool = True,
    dashboard_path: str = "/performance",
    enable_cors: bool = True,
    metrics: Optional[PerformanceMetrics] = None,
    metrics_factory: Optional[Callable[[], PerformanceMetrics]] = None,
):
    """
    Adds the performance monitoring middleware and dashboard to a FastAPI app.

    Args:
        app: The FastAPI application instance.
        enable_detailed_logging: If True, logs slow requests and errors.
        dashboard_path: The path where the performance dashboard will be served.
        enable_cors: If True, adds CORS middleware for dashboard access.
    """
    if metrics is not None and metrics_factory is not None:
        raise ValueError("Provide either 'metrics' or 'metrics_factory', not both.")

    metrics_instance = (
        metrics_factory() if metrics_factory is not None else metrics
    )
    if metrics_instance is None:
        metrics_instance = PerformanceMetrics()

    # 1. Add CORS middleware if enabled (for dashboard functionality)
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, specify your domain
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )

    # 2. Store metrics collector on application state for reuse
    setattr(app.state, METRICS_STATE_KEY, metrics_instance)

    # 3. Add the performance middleware
    app.add_middleware(
        PerformanceMiddleware, 
        metrics=metrics_instance,
        enable_detailed_logging=enable_detailed_logging
    )

    # 4. Include the metrics router bound to this metrics instance
    app.include_router(create_metrics_router(metrics_instance))

    # 5. Mount the static dashboard, finding its path within the package
    try:
        # This is the robust way to find package data files
        static_path = importlib.resources.files(__name__) / "static"
        
        # Convert to string path for StaticFiles compatibility
        static_path_str = str(static_path)
        
        # Mount static files directory
        app.mount(
            dashboard_path,
            StaticFiles(directory=static_path_str, html=True),
            name="performance_dashboard"
        )
        print(f"Performance dashboard mounted at: {dashboard_path}")
    except Exception as e:
        print(f"Warning: Could not mount performance dashboard: {e}")

# Expose a clean public API for the package
__all__ = ["add_performance_monitor", "PerformanceMetrics", "METRICS_STATE_KEY"]
