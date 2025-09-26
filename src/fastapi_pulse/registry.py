"""Endpoint discovery utilities for Pulse."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional

from fastapi import FastAPI

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
DEFAULT_MANAGEMENT_PREFIXES = {"/health/pulse"}


@dataclass(frozen=True)
class EndpointInfo:
    """Metadata describing an API endpoint derived from OpenAPI schema."""

    id: str
    method: str
    path: str
    summary: Optional[str]
    tags: List[str]
    requires_input: bool
    has_path_params: bool
    has_request_body: bool

    def to_dict(self) -> Dict[str, object]:
        """Serialize endpoint info for JSON responses."""
        data = asdict(self)
        return data


class PulseEndpointRegistry:
    """Caches endpoint metadata discovered from a FastAPI application's OpenAPI spec."""

    def __init__(self, app: FastAPI, *, exclude_prefixes: Iterable[str] | None = None) -> None:
        self.app = app
        self._endpoints: List[EndpointInfo] = []
        self._schema_hash: Optional[str] = None
        prefixes = set(DEFAULT_MANAGEMENT_PREFIXES)
        if exclude_prefixes:
            for prefix in exclude_prefixes:
                normalized = prefix if prefix.startswith('/') else f'/{prefix}'
                prefixes.add(normalized)
        self._exclude_prefixes = tuple(sorted(prefixes))

    def refresh(self) -> None:
        """Refresh endpoint metadata when OpenAPI schema changes."""
        schema = self.app.openapi()
        paths = schema.get("paths", {})
        schema_hash = hashlib.sha256(
            json.dumps(paths, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        if schema_hash == self._schema_hash:
            return

        endpoints: List[EndpointInfo] = []
        for path, operations in paths.items():
            if any(path.startswith(prefix) for prefix in self._exclude_prefixes):
                continue

            common_parameters = operations.get("parameters", []) if isinstance(operations, dict) else []

            if not isinstance(operations, dict):
                continue

            for method, operation in operations.items():
                if method.lower() == "parameters":
                    continue
                method_upper = method.upper()
                if method_upper not in ALLOWED_METHODS:
                    continue
                if not isinstance(operation, dict):
                    continue

                parameters = list(common_parameters)
                parameters.extend(operation.get("parameters", []))

                has_path_params = any(
                    (param.get("in") == "path" and param.get("required", False))
                    for param in parameters
                )
                has_request_body = bool(operation.get("requestBody"))
                requires_input = has_path_params or has_request_body

                endpoint = EndpointInfo(
                    id=f"{method_upper} {path}",
                    method=method_upper,
                    path=path,
                    summary=operation.get("summary") or operation.get("operationId"),
                    tags=operation.get("tags", []),
                    requires_input=requires_input,
                    has_path_params=has_path_params,
                    has_request_body=has_request_body,
                )
                endpoints.append(endpoint)

        endpoints.sort(key=lambda e: (e.path, e.method))
        self._endpoints = endpoints
        self._schema_hash = schema_hash

    def list_endpoints(self) -> List[EndpointInfo]:
        """Return all discovered endpoints."""
        self.refresh()
        return list(self._endpoints)

    def get_endpoint_map(self) -> Dict[str, EndpointInfo]:
        """Return endpoints keyed by their identifier."""
        return {endpoint.id: endpoint for endpoint in self.list_endpoints()}

    def auto_probe_targets(self) -> List[EndpointInfo]:
        """Return endpoints that can be automatically probed."""
        return [endpoint for endpoint in self.list_endpoints() if not endpoint.requires_input]
