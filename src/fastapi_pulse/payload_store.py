"""Persistent storage for Pulse probe payload overrides."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class PulsePayloadStore:
    """Manages persistent custom payload overrides for endpoints."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = threading.Lock()
        self._payloads: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self._payloads = data
        except Exception:
            # If the file is corrupted, ignore and start fresh.
            self._payloads = {}

    def _flush(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.file_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._payloads, handle, indent=2, ensure_ascii=False)
        tmp_path.replace(self.file_path)

    def get(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        return self._payloads.get(endpoint_id)

    def set(self, endpoint_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = self._sanitize_payload(payload)
        with self._lock:
            self._payloads[endpoint_id] = cleaned
            self._flush()
        return cleaned

    def delete(self, endpoint_id: str) -> None:
        with self._lock:
            if endpoint_id in self._payloads:
                del self._payloads[endpoint_id]
                self._flush()

    def all(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._payloads)

    @staticmethod
    def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        path_params = payload.get("path_params") or {}
        query_params = payload.get("query") or {}
        headers = payload.get("headers") or {}
        body = payload.get("body") if "body" in payload else None
        media_type = payload.get("media_type")

        return {
            "path_params": path_params,
            "query": query_params,
            "headers": headers,
            "body": body,
            "media_type": media_type,
        }


__all__ = ["PulsePayloadStore"]
