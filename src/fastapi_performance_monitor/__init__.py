"""
FastAPI Performance Monitor
===========================

A plug-and-play performance monitoring tool for FastAPI applications,
providing real-time metrics and a dashboard.
"""

__version__ = "0.1.2"

import importlib.resources
from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import the package components
from .middleware import PerformanceMiddleware
from .router import router as metrics_router

def add_performance_monitor(
    app: FastAPI, 
    enable_detailed_logging: bool = True,
    dashboard_path: str = "/performance",
    enable_cors: bool = True
):
    """
    Adds the performance monitoring middleware and dashboard to a FastAPI app.

    Args:
        app: The FastAPI application instance.
        enable_detailed_logging: If True, logs slow requests and errors.
        dashboard_path: The path where the performance dashboard will be served.
        enable_cors: If True, adds CORS middleware for dashboard access.
    """
    # 1. Add CORS middleware if enabled (for dashboard functionality)
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, specify your domain
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )

    # 2. Add the performance middleware
    app.add_middleware(
        PerformanceMiddleware, 
        enable_detailed_logging=enable_detailed_logging
    )

    # 3. Include the metrics router
    app.include_router(metrics_router)

    # 4. Mount the static dashboard, finding its path within the package
    try:
        # This is the robust way to find package data files
        static_path = importlib.resources.files(__name__) / "static"
        app.mount(
            dashboard_path,
            StaticFiles(directory=static_path, html=True),
            name="performance_dashboard"
        )
        print(f"Performance dashboard mounted at: {dashboard_path}")
    except Exception as e:
        print(f"Warning: Could not mount performance dashboard: {e}")

# Expose a clean public API for the package
__all__ = ["add_performance_monitor"]
