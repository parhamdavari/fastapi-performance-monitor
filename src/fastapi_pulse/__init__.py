"""
FastAPI Pulse
=============

Check your FastAPI's pulse with one line of code.
Instant health monitoring with a beautiful dashboard.
"""

from __future__ import annotations

__version__ = "0.2.0"

import importlib.resources
import logging
from pathlib import Path
from typing import Callable, Optional, Union

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .constants import (
    DEFAULT_PAYLOAD_CONFIG_FILENAME,
    PULSE_ENDPOINT_REGISTRY_KEY,
    PULSE_PAYLOAD_STORE_KEY,
    PULSE_PROBE_MANAGER_KEY,
    PULSE_STATE_KEY,
)
from .metrics import PulseMetrics
from .middleware import PulseMiddleware
from .payload_store import PulsePayloadStore
from .probe import PulseProbeManager
from .registry import PulseEndpointRegistry
from .router import create_pulse_router

logger = logging.getLogger(__name__)

def add_pulse(
    app: FastAPI,
    enable_detailed_logging: bool = True,
    dashboard_path: str = "/pulse",
    enable_cors: bool = True,
    metrics: Optional[PulseMetrics] = None,
    metrics_factory: Optional[Callable[[], PulseMetrics]] = None,
    payload_config_path: Optional[Union[Path, str]] = None,
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

    payload_path = Path(payload_config_path) if payload_config_path else Path(app.root_path) / DEFAULT_PAYLOAD_CONFIG_FILENAME
    payload_store = PulsePayloadStore(payload_path)
    setattr(app.state, PULSE_PAYLOAD_STORE_KEY, payload_store)

    probe_manager = PulseProbeManager(
        app,
        metrics_instance,
        registry=registry,
        payload_store=payload_store,
    )
    setattr(app.state, PULSE_PROBE_MANAGER_KEY, probe_manager)

    # 4. Add the pulse middleware
    app.add_middleware(
        PulseMiddleware,
        metrics=metrics_instance,
        enable_detailed_logging=enable_detailed_logging,
        exclude_path_prefixes=exclude_prefixes,
    )

    # 5. Include the pulse router bound to this metrics instance
    app.include_router(create_pulse_router(metrics_instance), include_in_schema=False)

    # 6. Mount the static dashboard, finding its path within the package
    try:
        # This is the robust way to find package data files
        try:
            static_path = importlib.resources.files(__name__) / "static"  # type: ignore[attr-defined]
            static_path_str = str(static_path)
        except AttributeError:
            with importlib.resources.path(__name__, "static") as data_path:
                static_path_str = str(data_path)

        # Mount static files directory
        app.mount(
            dashboard_path,
            StaticFiles(directory=static_path_str, html=True),
            name="pulse_dashboard"
        )
        logger.info("Pulse dashboard mounted at %s", dashboard_path)
    except Exception as e:
        logger.warning("Could not mount pulse dashboard: %s", e)

# Expose a clean public API for the package
__all__ = [
    "add_pulse",
    "PulseMetrics",
    "PULSE_STATE_KEY",
    "PULSE_ENDPOINT_REGISTRY_KEY",
    "PULSE_PAYLOAD_STORE_KEY",
    "PULSE_PROBE_MANAGER_KEY",
]
