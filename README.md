# FastAPI Pulse

> Keep an eye on your FastAPI app with one joyful line.

[![PyPI](https://badge.fury.io/py/fastapi-pulse.svg)](https://pypi.org/project/fastapi-pulse/)
[![Python](https://img.shields.io/pypi/pyversions/fastapi-pulse.svg?logo=python&logoColor=ffdd54)](https://pypi.org/project/fastapi-pulse/)
[![CI](https://github.com/parhamdavari/fastapi-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/parhamdavari/fastapi-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-1c7ed6.svg)](./LICENSE)

FastAPI Pulse makes monitoring feel natural: drop in `add_pulse(app)` and you instantly get live dashboards, smart probes, and a CLI that plays nicely with CI/CD. No boilerplate. No config jungle. Just signal.

---

## Two-Breath Install

```bash
pip install fastapi-pulse
```

```python
from fastapi import FastAPI
from fastapi_pulse import add_pulse

app = FastAPI()
add_pulse(app)  # monitor, dashboard, probes – all unlocked
```

Want the CLI too? `pip install "fastapi-pulse[cli]"`

---

## Why People Love It

- **One-line setup** – call `add_pulse(app)` and ship it.
- **Peaceful defaults** – zero configuration for the common path.
- **Live dashboard** – `/pulse` shows latency, throughput, success rates.
- **Probing built-in** – discover endpoints and fire health checks from the UI or CLI.
- **Production-safe** – TDigest percentiles, rolling windows, no memory leaks.

---

## What You Get

| Experience                | Endpoint                          |
|--------------------------|----------------------------------|
| Friendly dashboard       | `GET /pulse`                     |
| Endpoint explorer        | `GET /pulse/endpoints.html`      |
| JSON metrics             | `GET /health/pulse`              |
| Probe registry           | `GET /health/pulse/endpoints`    |
| Trigger a probe          | `POST /health/pulse/probe`       |
| Check probe status       | `GET /health/pulse/probe/{id}`   |

Add your own monitors using the JSON API or wire it into your favorite alerting tool—the payload mirrors what the dashboard sees.

---

## Tiny Tweaks When You Need Them

```python
add_pulse(
    app,
    dashboard_path="/pulse",          # move the UI
    enable_detailed_logging=False,    # quiet production logs
    payload_config_path="pulse_probes.json",  # persist probe payloads
)
```

Prefer a custom metrics window?

```python
from fastapi_pulse import PulseMetrics

metrics = PulseMetrics(window_seconds=600)
add_pulse(app, metrics=metrics)
```

---

## CLI In Your Pocket

```bash
pulse-cli check http://localhost:8000
pulse-cli check https://api.example.com --fail-on-error --format json
```

📚 Dive deeper in [CLI_README.md](./CLI_README.md).

---

## Trying the TestPyPI Build

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            fastapi-pulse==0.2.0
python -c "import fastapi_pulse; print(fastapi_pulse.__version__)"
```

FastAPI Pulse is intentionally light—keep the virtualenv clean, and you can flip between published builds in seconds.

---

## Contribute With Ease

Issues and pull requests are welcome. The guiding principle is the same as the product: simple, helpful, and kind to the next developer.

---

## License

MIT © [Parham Davari](./LICENSE)
