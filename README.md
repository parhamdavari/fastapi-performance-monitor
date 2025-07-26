<div align="center">

# FastAPI Performance Monitor

A simple, plug-and-play performance monitoring tool for FastAPI applications
<br />
that provides real-time metrics and a dashboard with zero configuration.

[![CI](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/fastapi-performance-monitor.svg)](https://badge.fury.io/py/fastapi-performance-monitor)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastapi-performance-monitor)](https://img.shields.io/pypi/pyversions/fastapi-performance-monitor)
[![PyPI - License](https://img.shields.io/pypi/l/fastapi-performance-monitor)](https://img.shields.io/pypi/l/fastapi-performance-monitor)

</div>

---

## → Getting Started

### Installation

```bash
pip install fastapi-performance-monitor
```

### Usage

In your main application file, import and apply `add_performance_monitor` to your FastAPI app instance.

```python
# main.py
from fastapi import FastAPI
from fastapi_performance_monitor import add_performance_monitor

app = FastAPI()

# Add this single line to enable the monitor
add_performance_monitor(app)

@app.get("/")
def read_root():
    return {"message": "Hello World"}
```

## → Endpoints

Once your application is running, the following endpoints will be available:

- **Dashboard**: `http://localhost:8000/performance`
- **Metrics**: `http://localhost:8000/health/metrics`

The dashboard provides a user-friendly interface to view the metrics, while the JSON endpoint allows for programmatic access, perfect for integrating with alerting or other monitoring systems.
