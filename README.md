# FastAPI Performance Monitor

[![CI](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-performance-monitor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/parhamdavari/fastapi-performance-monitor/graph/badge.svg)](https://codecov.io/gh/parhamdavari/fastapi-performance-monitor)
[![PyPI version](https://badge.fury.io/py/fastapi-performance-monitor.svg)](https://badge.fury.io/py/fastapi-performance-monitor)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastapi-performance-monitor)
![PyPI - License](https://img.shields.io/pypi/l/fastapi-performance-monitor)

A simple, plug-and-play performance monitoring tool for FastAPI applications, providing real-time metrics and a dashboard with zero configuration.

---

<pre>
╔═════════════════════════════════════════════════════════════════════════════╗
║ <b>FastAPI Performance Dashboard</b>                                                 ║
╠════════════════════════════════╦════════════════════════════════════════════╣
║ <b>SLA Compliance</b>                 ║ <b>Overall Metrics</b>                            ║
║   Latency SLA Met: <font color="green">true</font>         ║   Total Requests: 1,245                      ║
║   Availability SLA Met: <font color="green">true</font>    ║   Success Count: 1,230 (98.8%)               ║
║                                ║   Error Count: 15 (1.2%)                     ║
╠════════════════════════════════╩════════════════════════════════════════════╣
║ <b>Endpoint Metrics (GET /items/{item_id})</b>                                 ║
╠════════════════════════════════╦════════════════════════════════════════════╣
║   Total Requests: 834          ║   P50 Response Time: 52 ms                   ║
║   Success Count: 830           ║   P90 Response Time: 110 ms                  ║
║   Error Count: 4               ║   P95 Response Time: 154 ms                  ║
║                                ║   P99 Response Time: 230 ms                  ║
╚════════════════════════════════╩════════════════════════════════════════════╝
</pre>

---

## Features

- **Zero Configuration:** Add a single line of code to your app to get started.
- **Real-time Metrics:** Tracks total requests, success/error counts, and error rates.
- **Latency Percentiles:** Calculates P50, P90, P95, and P99 response times to give you a clear picture of your application's responsiveness.
- **SLA Monitoring:** Automatically determines if your application is meeting its latency and availability service-level agreements (SLAs).
- **Interactive Dashboard:** A clean, real-time dashboard to visualize all performance metrics.
- **Lightweight:** Designed to have a minimal performance impact on your application.

## Installation

```bash
pip install fastapi-performance-monitor
```

## Quick Start

In your main application file, import `add_performance_monitor` and apply it to your FastAPI app instance.

```python
# main.py
from fastapi import FastAPI
from fastapi_performance_monitor import add_performance_monitor
import time
import random

app = FastAPI()

# Add this single line to enable the monitor
add_performance_monitor(app)

@app.get("/")
def read_root():
    # Simulate some work
    time.sleep(random.uniform(0.05, 0.5))
    return {"message": "Hello World"}

@app.get("/error")
def cause_error():
    raise ValueError("This is a test error")
```

Once your application is running, the following endpoints will be available:

- **Performance Dashboard**: `http://localhost:8000/performance`
- **Metrics API Endpoint**: `http://localhost:8000/health/metrics`

The dashboard provides a user-friendly interface to view the metrics, while the JSON endpoint allows for programmatic access, perfect for integrating with alerting or other monitoring systems.
