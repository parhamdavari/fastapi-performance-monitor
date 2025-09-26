# FastAPI Pulse

Check your FastAPI's pulse with one line of code. Instant health monitoring with a beautiful dashboard.

[![CI](https://github.com/parhamdavari/fastapi-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-pulse/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/fastapi-pulse.svg)](https://pypi.org/project/fastapi-pulse/)

---

## Why FastAPI Pulse?

- **One line setup**: `add_pulse(app)` and you're monitoring
- **Zero configuration**: Sensible defaults, works out of the box
- **Beautiful dashboard**: Live metrics at `/pulse`
- **Production ready**: Rolling windows, efficient percentiles, zero memory leaks
- **Developer friendly**: Logs slow requests and errors automatically

## Quickstart

```bash
pip install fastapi-pulse
```

```python
from fastapi import FastAPI
from fastapi_pulse import add_pulse

app = FastAPI()
add_pulse(app)  # That's it!

@app.get("/")
def read_root():
    return {"message": "Hello, world!"}
```

## Your API's Vital Signs

| What                    | Where                |
|------------------------|----------------------|
| 📊 **Live Dashboard**   | `GET /pulse`         |
| 🔍 **JSON Metrics**     | `GET /health/pulse`  |

The dashboard shows your API's heartbeat in real-time. The JSON endpoint gives you raw data for alerts and automation.

## Configuration

```python
add_pulse(
    app,
    enable_detailed_logging=True,  # Log slow requests (>1s) and errors
    dashboard_path="/pulse",       # Where to mount the dashboard
    enable_cors=True,              # Allow cross-origin requests
)
```

## What Gets Measured

**Request Metrics**:

- Latency percentiles (P95, P99)
- Request count and error rates
- Response time distribution

**Smart Grouping**:

- `/users/123` → `/users/{id}`
- `/api/v1/posts/456` → `/api/v1/posts/{id}`

**Rolling Windows**: Metrics automatically expire after 5 minutes, preventing memory leaks in long-running applications.

## Custom Metrics (Advanced)

```python
from fastapi_pulse import add_pulse, PulseMetrics

# Create custom metrics collector
metrics = PulseMetrics(window_seconds=600)  # 10-minute window
add_pulse(app, metrics=metrics)

# Access metrics in your routes
@app.get("/custom")
def custom_endpoint():
    pulse_metrics = app.state.fastapi_pulse_metrics
    stats = pulse_metrics.get_metrics()
    return {"current_load": stats["summary"]["total_requests"]}
```

## Production Tips

- Enable `enable_detailed_logging=False` in production to reduce log noise
- Use the JSON endpoint (`/health/pulse`) for monitoring systems like Prometheus
- The dashboard is optimized for development; build custom dashboards using the JSON API for production

## Contributing

Issues and pull requests welcome! This tool is designed to be simple and reliable.

## License

MIT License - see `LICENSE` file for details.
