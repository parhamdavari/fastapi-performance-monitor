# FastAPI Performance Monitor

Lightweight drop-in monitoring for FastAPI apps with live metrics and a bundled dashboard.

[![CI](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/fastapi-performance-monitor.svg)](https://pypi.org/project/fastapi-performance-monitor/)

---

## Features

- Instrument any FastAPI project with a single helper call.
- Collect latency, throughput, error-rate, and percentile metrics without extra storage.
- Serve a static dashboard and JSON API for dashboards, alerting, or automation.
- Ships with sensible defaults yet allows request logging and CORS customization.

## Install

```bash
pip install fastapi-performance-monitor
```

## Quickstart

```python
from fastapi import FastAPI
from fastapi_performance_monitor import add_performance_monitor

app = FastAPI()
add_performance_monitor(app)

@app.get("/")
def read_root():
    return {"message": "Hello, world!"}
```

## Dashboard & Metrics Endpoints

| Purpose    | Path                              |
|------------|-----------------------------------|
| Dashboard  | `GET /performance`                |
| Metrics    | `GET /health/metrics`             |

The dashboard provides a minimal UI for live inspection. The JSON endpoint exposes the same data for external tools.

## Configuration

`add_performance_monitor(app, enable_detailed_logging=True, dashboard_path="/performance", enable_cors=True)`

- `enable_detailed_logging`: flag slow requests (>1s) and error responses in logs.
- `dashboard_path`: mount point for the static dashboard assets.
- `enable_cors`: relaxes CORS for the dashboard; tighten it for production if needed.

## Contributing

Issues and pull requests are welcome. See `CONTRIBUTING.md` for local setup and tooling expectations.

## License

Released under the MIT License. See `LICENSE` for details.
