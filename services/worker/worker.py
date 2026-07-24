"""
Ouroboros demo fleet — load worker.

Continuously calls the API's /orders endpoint so that injected faults show up
as real latency/error/throughput signal in SigNoz (otherwise an idle service
produces no data to alert on). Auto-instrumented via opentelemetry-instrument.
"""
import os
import time

import httpx

API_URL = os.getenv("API_URL", "http://demo-api:8000")


def main():
    client = httpx.Client(timeout=10.0)
    while True:
        try:
            client.get(f"{API_URL}/orders")
        except Exception as e:  # noqa: BLE001 - keep the loop alive for the demo
            print(f"worker request failed: {e}", flush=True)
        time.sleep(0.5)  # ~2 req/s, steady baseline


if __name__ == "__main__":
    main()
