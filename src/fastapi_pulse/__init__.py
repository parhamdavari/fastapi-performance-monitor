"""
FastAPI Pulse
=============

Check your FastAPI's pulse with one line of code.
Instant health monitoring with a beautiful dashboard.
"""

__version__ = "0.2.0"

import importlib.resources
from typing import Callable, Optional

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .metrics import PulseMetrics
from .middleware import PulseMiddleware
from .registry import PulseEndpointRegistry
from .probe import PulseProbeManager
from .router import create_pulse_router
from .constants import (
    PULSE_ENDPOINT_REGISTRY_KEY,
    PULSE_PROBE_MANAGER_KEY,
    PULSE_STATE_KEY,
)

def add_pulse(
    app: FastAPI,
    enable_detailed_logging: bool = True,
    dashboard_path: str = "/pulse",
    enable_cors: bool = True,
    metrics: Optional[PulseMetrics] = None,
    metrics_factory: Optional[Callable[[], PulseMetrics]] = None,
):
    """
    Adds pulse monitoring to your FastAPI app with one line of code.

    Args:
        app: The FastAPI application instance.
        enable_detailed_logging: If True, logs slow requests and errors.
        dashboard_path: The path where the pulse dashboard will be served.
        enable_cors: If True, adds CORS middleware for dashboard access.
    """
    if metrics is not None and metrics_factory is not None:
        raise ValueError("Provide either 'metrics' or 'metrics_factory', not both.")

    metrics_instance = (
        metrics_factory() if metrics_factory is not None else metrics
    )
    if metrics_instance is None:
        metrics_instance = PulseMetrics()

    # 1. Add CORS middleware if enabled (for dashboard functionality)
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, specify your domain
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )

    # 2. Store pulse collector on application state for reuse
    setattr(app.state, PULSE_STATE_KEY, metrics_instance)

    # Determine which paths should be excluded from metric tracking
    dashboard_prefix = dashboard_path if dashboard_path.startswith('/') else f'/{dashboard_path}'
    dashboard_prefix = dashboard_prefix.rstrip('/') or '/'
    exclude_prefixes = (
        '/health/pulse',
        dashboard_prefix,
    )

    # 3. Create endpoint registry and probe manager
    registry = PulseEndpointRegistry(app, exclude_prefixes=exclude_prefixes)
    setattr(app.state, PULSE_ENDPOINT_REGISTRY_KEY, registry)
    probe_manager = PulseProbeManager(app, metrics_instance)
    setattr(app.state, PULSE_PROBE_MANAGER_KEY, probe_manager)

    # 4. Add the pulse middleware
    app.add_middleware(
        PulseMiddleware,
        metrics=metrics_instance,
        enable_detailed_logging=enable_detailed_logging,
        exclude_path_prefixes=exclude_prefixes,
    )

    # 5. Include the pulse router bound to this metrics instance
    app.include_router(create_pulse_router(metrics_instance))

    # 6. Mount the static dashboard, finding its path within the package
    try:
        # This is the robust way to find package data files
        static_path = importlib.resources.files(__name__) / "static"
        
        # Convert to string path for StaticFiles compatibility
        static_path_str = str(static_path)
        
        # Mount static files directory
        app.mount(
            dashboard_path,
            StaticFiles(directory=static_path_str, html=True),
            name="pulse_dashboard"
        )
        print(f"Pulse dashboard mounted at: {dashboard_path}")
    except Exception as e:
        print(f"Warning: Could not mount pulse dashboard: {e}")

# Expose a clean public API for the package
__all__ = [
    "add_pulse",
    "PulseMetrics",
    "PULSE_STATE_KEY",
    "PULSE_ENDPOINT_REGISTRY_KEY",
    "PULSE_PROBE_MANAGER_KEY",
]
