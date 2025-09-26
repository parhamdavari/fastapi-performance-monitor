"""Shared constants for Pulse state keys."""

PULSE_STATE_KEY = "fastapi_pulse_metrics"
PULSE_ENDPOINT_REGISTRY_KEY = "fastapi_pulse_endpoint_registry"
PULSE_PROBE_MANAGER_KEY = "fastapi_pulse_probe_manager"
PULSE_PAYLOAD_STORE_KEY = "fastapi_pulse_payload_store"

DEFAULT_PAYLOAD_CONFIG_FILENAME = "pulse_probes.json"


__all__ = [
    "PULSE_STATE_KEY",
    "PULSE_ENDPOINT_REGISTRY_KEY",
    "PULSE_PROBE_MANAGER_KEY",
    "PULSE_PAYLOAD_STORE_KEY",
    "DEFAULT_PAYLOAD_CONFIG_FILENAME",
]
