"""Sample payload generator based on OpenAPI schemas."""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional

from .registry import EndpointInfo


class SamplePayloadBuilder:
    def __init__(self, openapi_schema: Dict[str, Any]):
        self.openapi_schema = openapi_schema or {}
        self.components = self.openapi_schema.get("components", {})

    def build(self, endpoint: EndpointInfo) -> Dict[str, Any]:
        path_params = {
            param["name"]: self._value_for_parameter(param)
            for param in endpoint.path_parameters
        }
        query_params = {
            param["name"]: self._value_for_parameter(param)
            for param in endpoint.query_parameters
        }
        headers = {
            param["name"]: self._value_for_parameter(param)
            for param in endpoint.header_parameters
        }

        body = None
        if endpoint.request_body_schema is not None:
            body = self._value_from_schema(endpoint.request_body_schema)

        return {
            "path_params": path_params,
            "query": query_params,
            "headers": headers,
            "body": body,
            "media_type": endpoint.request_body_media_type,
        }

    def _value_for_parameter(self, parameter: Dict[str, Any]) -> Any:
        if "example" in parameter:
            return parameter["example"]
        schema = parameter.get("schema", {})
        if not schema and "content" in parameter:
            # Parameter with content entry; pick first schema.
            content = parameter["content"]
            if isinstance(content, dict) and content:
                schema = next(iter(content.values())).get("schema", {})
        return self._value_from_schema(schema)

    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        if not ref or not ref.startswith("#/"):
            return {}
        parts = ref.lstrip("#/").split("/")
        current: Any = self.openapi_schema
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
            if current is None:
                break
        return current or {}

    def _value_from_schema(self, schema: Optional[Dict[str, Any]], depth: int = 0) -> Any:
        if not schema or depth > 8:
            return "sample"
        if "$ref" in schema:
            resolved = self._resolve_ref(schema["$ref"])
            if resolved:
                return self._value_from_schema(resolved, depth + 1)
        if "default" in schema:
            return schema["default"]
        if "example" in schema:
            return schema["example"]
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        schema_type = schema.get("type")
        fmt = schema.get("format")
        if schema_type == "string":
            if fmt == "date-time":
                return _dt.datetime.utcnow().isoformat() + "Z"
            if fmt == "date":
                return _dt.date.today().isoformat()
            if fmt == "email":
                return "user@example.com"
            if fmt == "uuid":
                return "00000000-0000-0000-0000-000000000000"
            return "sample"
        if schema_type == "integer":
            return 1
        if schema_type == "number":
            return 1.0
        if schema_type == "boolean":
            return True
        if schema_type == "array":
            items = schema.get("items", {})
            return [self._value_from_schema(items, depth + 1)]
        if schema_type == "object" or "properties" in schema:
            properties = schema.get("properties", {})
            result = {}
            for key, subschema in properties.items():
                result[key] = self._value_from_schema(subschema, depth + 1)
            additional = schema.get("additionalProperties")
            if isinstance(additional, dict) and not result:
                result["key"] = self._value_from_schema(additional, depth + 1)
            return result
        any_of = schema.get("anyOf") or schema.get("oneOf")
        if isinstance(any_of, list) and any_of:
            return self._value_from_schema(any_of[0], depth + 1)
        return "sample"


__all__ = ["SamplePayloadBuilder"]
