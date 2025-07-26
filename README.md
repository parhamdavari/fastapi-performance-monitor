# FastAPI Performance Monitor

[![CI](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/fastapi-performance-monitor.svg)](https://badge.fury.io/py/fastapi-performance-monitor)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastapi-performance-monitor)
![PyPI - License](https://img.shields.io/pypi/l/fastapi-performance-monitor)

A plug-and-play performance monitoring tool for FastAPI applications, providing real-time metrics and a dashboard.

## Installation

```bash
pip install fastapi-performance-monitor
```

## Usage

In your `main.py`, import the `add_performance_monitor` function and add it to your FastAPI app.

```python
from fastapi import FastAPI
from fastapi_performance_monitor import add_performance_monitor

app = FastAPI()

# Add this single line to enable everything
add_performance_monitor(app)

@app.get("/")
def read_root():
    return {"message": "Hello World"}
```

That's it! Your application is now being monitored.

- **Metrics Endpoint**: `http://localhost:8000/health/metrics`
- **Dashboard**: `http://localhost:8000/performance`

## Features

- Real-time performance metrics (request count, error rate, response times).
- P95 and P99 latency calculations.
- Interactive dashboard to visualize metrics.
- Easy to integrate with any FastAPI project.
