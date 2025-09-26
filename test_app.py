#!/usr/bin/env python3
"""Comprehensive playground app for exercising FastAPI Pulse features.

Run with: ``python test_app.py`` and explore the endpoints to generate
different traffic profiles (fast, slow, failing, streaming, background
tasks, etc.).
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Dict, List

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fastapi_pulse import add_pulse


class ProductIn(BaseModel):
    name: str = Field(..., example="Pulse Monitor")
    price: float = Field(..., ge=0, example=49.99)
    tags: List[str] = Field(default_factory=list, example=["monitoring", "fastapi"])


class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class OrderOut(OrderIn):
    order_id: int
    status: str


app = FastAPI(title="FastAPI Pulse Playground")
add_pulse(app, enable_detailed_logging=True)


# In-memory stores (not for production!)
PRODUCT_DB: Dict[int, ProductIn] = {
    1: ProductIn(name="Pulse Dashboard", price=0.0, tags=["demo"]),
    2: ProductIn(name="Latency Analyzer", price=49.0, tags=["tool", "latency"]),
}
ORDER_DB: Dict[int, OrderOut] = {}
ORDER_EVENTS: deque[str] = deque(maxlen=25)


@app.get("/")
async def root() -> Dict[str, str]:
    await asyncio.sleep(0.05)  # mimic minor async work
    return {"message": "Welcome to the Pulse playground"}


@app.get("/slow")
async def slow_endpoint(delay: float = 1.5) -> Dict[str, float]:
    """Simulate a slow endpoint by sleeping for ``delay`` seconds."""
    await asyncio.sleep(delay)
    return {"duration": delay}


@app.get("/flaky")
async def flaky_endpoint() -> Dict[str, str]:
    """Randomly succeed or fail to mimic unstable integrations."""
    await asyncio.sleep(0.1)
    if random.random() < 0.3:
        raise HTTPException(status_code=503, detail="Upstream service unavailable")
    return {"status": "ok"}


@app.get("/products")
async def list_products() -> Dict[str, List[ProductIn]]:
    return {"items": list(PRODUCT_DB.values())}


@app.post("/products", status_code=201)
async def create_product(product: ProductIn) -> Dict[str, ProductIn]:
    product_id = max(PRODUCT_DB.keys()) + 1
    PRODUCT_DB[product_id] = product
    return {"product_id": product_id, "product": product}


@app.get("/products/{product_id}")
async def get_product(product_id: int) -> ProductIn:
    product = PRODUCT_DB.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(order: OrderIn, background_tasks: BackgroundTasks) -> OrderOut:
    if order.product_id not in PRODUCT_DB:
        raise HTTPException(status_code=404, detail="Product not found")

    order_id = max(ORDER_DB.keys(), default=1000) + 1
    order_out = OrderOut(order_id=order_id, status="queued", **order.dict())
    ORDER_DB[order_id] = order_out

    background_tasks.add_task(_simulate_order_fulfillment, order_id)
    ORDER_EVENTS.appendleft(f"Order {order_id} queued")
    return order_out


@app.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int) -> OrderOut:
    order = ORDER_DB.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/orders/events")
async def order_events() -> Dict[str, List[str]]:
    return {"events": list(ORDER_EVENTS)}


async def _simulate_order_fulfillment(order_id: int) -> None:
    await asyncio.sleep(0.5)
    order = ORDER_DB.get(order_id)
    if order:
        order.status = "processing"
        ORDER_EVENTS.appendleft(f"Order {order_id} processing")

    await asyncio.sleep(0.7)
    order = ORDER_DB.get(order_id)
    if order:
        order.status = "fulfilled"
        ORDER_EVENTS.appendleft(f"Order {order_id} fulfilled")


@app.get("/stream")
async def stream_numbers(limit: int = 5) -> StreamingResponse:
    """Return a streaming response for testing chunked transfers."""

    async def number_generator():
        for i in range(1, limit + 1):
            await asyncio.sleep(0.25)
            yield f"data: {i}\n"

    return StreamingResponse(number_generator(), media_type="text/event-stream")


@app.get("/error")
def error_endpoint() -> Dict[str, str]:
    """Endpoint that raises an exception to test error paths."""
    raise RuntimeError("Intentional test error")


@app.get("/cpu-intensive")
def cpu_intensive() -> Dict[str, float]:
    """CPU-intensive endpoint performing heavy synchronous work."""
    start = time.perf_counter()
    _ = sum(i * i for i in range(200_000))
    duration = time.perf_counter() - start
    return {"duration": duration}


if __name__ == "__main__":
    print("🔮 Starting FastAPI Pulse playground...")
    print("Key endpoints:")
    print("  GET /                   - Hello world + light async work")
    print("  GET /slow?delay=2       - Simulated slow response")
    print("  GET /flaky              - Random 70% success")
    print("  GET /products           - List catalog items")
    print("  GET /products/{id}      - Fetch a product")
    print("  POST /products          - Create a product")
    print("  POST /orders            - Create order (background tasks)")
    print("  GET /orders/{id}        - Poll order status")
    print("  GET /orders/events      - View latest order events")
    print("  GET /stream             - Streaming numbers (SSE style)")
    print("  GET /cpu-intensive      - Stress CPU-bound path")
    print("  GET /error              - Trigger failure path")
    print("  Dashboard 👉 GET /pulse")
    print("  Metrics   👉 GET /health/pulse")
    print("\n✨ Visit http://localhost:8000/pulse for the live dashboard")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
