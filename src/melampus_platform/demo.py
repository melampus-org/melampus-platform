"""Synthetic checkout traffic with outcomes evaluated by the real Melampus SDK."""

from __future__ import annotations

import time
from typing import Any

from melampus import Check, Policy, instrumented
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Tracer


def generate(provider: TracerProvider, count: int = 24) -> dict[str, Any]:
    tracer: Tracer = provider.get_tracer("melampus.demo", "0.1.0")

    @instrumented(
        intent="Calculate a nonnegative price and apply a discount of at most twenty percent.",
        checks=(
            Check("nonnegative-total", lambda r: r >= 0, "The checkout total is nonnegative."),
            Check(
                "discount-ceiling",
                lambda r: r >= 80,
                "The checkout total is at least eighty for a one hundred dollar basket.",
            ),
        ),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.pricing:calculate_total",
    )
    def price(discount: float) -> float:
        time.sleep(0.002)
        return 100 * (1 - discount)

    @instrumented(
        intent="Reserve a positive quantity of inventory.",
        checks=(Check("stock-reserved", lambda r: r > 0, "At least one unit is reserved."),),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.inventory:reserve_stock",
    )
    def reserve(quantity: int) -> int:
        time.sleep(0.001)
        return quantity

    @instrumented(
        intent="Return a valid payment authorization.",
        checks=(Check("payment-authorized", lambda r: r is True, "Payment is authorized."),),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.payments:authorize",
    )
    def authorize(broken: bool) -> bool:
        time.sleep(0.003)
        if broken:
            raise RuntimeError("Synthetic payment failure")
        return True

    @instrumented(
        intent="Calculate shipping cost within its configured check budget.",
        checks=(Check("shipping-nonnegative", lambda r: r >= 0, "Shipping is nonnegative."),),
        policy=Policy(checks_per_second=0),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.shipping:calculate_shipping",
    )
    def shipping() -> int:
        return 5

    @instrumented(
        intent="Complete checkout with a valid order identifier.",
        checks=(
            Check(
                "order-created",
                lambda r: r.startswith("order-"),
                "Order identifiers have the order prefix.",
            ),
        ),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.orders:submit_order",
    )
    def checkout(index: int) -> str:
        price(0.35 if index % 5 == 0 else 0.1)
        reserve(0 if index % 11 == 0 else 1)
        authorize(index % 13 == 0)
        if index % 7 == 0:
            shipping()
        return f"order-{index:04d}"

    trace_ids = []
    for i in range(count):
        with tracer.start_as_current_span(
            "checkout.request", record_exception=False, set_status_on_exception=False
        ) as root:
            trace_ids.append(f"{root.get_span_context().trace_id:032x}")
            try:
                checkout(i)
            except RuntimeError:
                pass
    provider.force_flush()
    return {"generated_traces": count, "trace_ids": trace_ids, "synthetic": True}
