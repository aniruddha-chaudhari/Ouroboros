"""
Ouroboros demo fleet — API service ("the patient").

A tiny FastAPI service that talks to MongoDB and a worker. It exposes a
/fault control plane so we can deterministically inject the failures the
Ouroboros agent will detect, diagnose, and heal.

Telemetry: this service is auto-instrumented at launch via
`opentelemetry-instrument` (see services/api/run.sh), so FastAPI, HTTP,
logging and PyMongo spans/metrics/logs flow to SigNoz with zero code here.
We only add a couple of manual spans to make the demo trace read clearly.
"""
import asyncio
import os
import random

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel
from pymongo import MongoClient

tracer = trace.get_tracer("ouroboros.demo.api")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
db = mongo["ouroboros"]

app = FastAPI(title="Ouroboros Demo API")

# --- Fault control plane ----------------------------------------------------
# The agent's action tools flip these back to healthy values as its "remediation".
FAULTS = {
    "latency_ms": 0,       # injected artificial latency per request
    "error_rate": 0.0,     # fraction of requests that 500
    "mem_leak": False,     # leak memory on each request
}
_leak: list[bytes] = []


class FaultSpec(BaseModel):
    latency_ms: int | None = None
    error_rate: float | None = None
    mem_leak: bool | None = None


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/fault")
def set_fault(spec: FaultSpec):
    """Inject or clear a fault. The agent calls this (via action tools) to heal."""
    if spec.latency_ms is not None:
        FAULTS["latency_ms"] = spec.latency_ms
    if spec.error_rate is not None:
        FAULTS["error_rate"] = spec.error_rate
    if spec.mem_leak is not None:
        FAULTS["mem_leak"] = spec.mem_leak
        if not spec.mem_leak:
            _leak.clear()
    return {"faults": FAULTS}


@app.get("/fault")
def get_fault():
    return {"faults": FAULTS}


@app.get("/orders")
async def list_orders():
    """Main business endpoint — this is what degrades when a fault is active."""
    with tracer.start_as_current_span("handle_orders") as span:
        span.set_attribute("app.endpoint", "orders")

        if FAULTS["mem_leak"]:
            _leak.append(b"x" * 5_000_000)  # 5MB per call
            span.set_attribute("app.mem_leak_chunks", len(_leak))

        # Independent per-request failure — real randomness, so the error rate
        # in telemetry actually matches FAULTS["error_rate"] (not a time bucket).
        if FAULTS["error_rate"] and random.random() < FAULTS["error_rate"]:
            span.set_attribute("error", True)
            raise HTTPException(status_code=500, detail="synthetic downstream failure")

        with tracer.start_as_current_span("db_query") as qspan:
            # A latency fault is modeled as a SLOW QUERY: the delay lands on the
            # db_query span itself, so "slow database query" is a true, trace-
            # visible root cause rather than a bare sleep in the handler.
            if FAULTS["latency_ms"]:
                await asyncio.sleep(FAULTS["latency_ms"] / 1000.0)
                qspan.set_attribute("app.injected_latency_ms", FAULTS["latency_ms"])
            docs = list(db.orders.find({}, {"_id": 0}).limit(10))
        return {"orders": docs, "count": len(docs)}


@app.on_event("startup")
def seed():
    if db.orders.count_documents({}) == 0:
        db.orders.insert_many([{"id": i, "item": f"sku-{i}", "qty": i} for i in range(10)])
