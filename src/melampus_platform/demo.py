"""Synthetic checkout traffic with outcomes evaluated by the real Melampus SDK."""

from __future__ import annotations

import time
from typing import Any

from melampus import Check, Contract, Policy, instrumented
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Tracer

from .catalog import from_contracts

DEMO_CONTRACTS = {
    "checkout.pricing:calculate_total": Contract(
        "Calculate a nonnegative price and apply a discount of at most twenty percent.",
        (
            Check("nonnegative-total", lambda r: r >= 0, "The checkout total is nonnegative."),
            Check(
                "discount-ceiling",
                lambda r: r >= 80,
                "The checkout total is at least eighty for a one hundred dollar basket.",
            ),
        ),
    ),
    "checkout.inventory:reserve_stock": Contract(
        "Reserve a positive quantity of inventory.",
        (Check("stock-reserved", lambda r: r > 0, "At least one unit is reserved."),),
    ),
    "checkout.payments:authorize": Contract(
        "Return a valid payment authorization.",
        (Check("payment-authorized", lambda r: r is True, "Payment is authorized."),),
    ),
    "checkout.shipping:calculate_shipping": Contract(
        "Calculate shipping cost within its configured check budget.",
        (Check("shipping-nonnegative", lambda r: r >= 0, "Shipping is nonnegative."),),
    ),
    "checkout.orders:submit_order": Contract(
        "Complete checkout with a valid order identifier.",
        (
            Check(
                "order-created",
                lambda r: r.startswith("order-"),
                "Order identifiers have the order prefix.",
            ),
        ),
    ),
    "checkout.reconciliation:reconcile_settlement": Contract(
        "Reconcile authorized payments with recorded orders.",
        (
            Check(
                "settlement-balanced",
                lambda r: r is True,
                "Every authorized payment has a matching order.",
            ),
        ),
    ),
}


def demo_catalog() -> dict[str, Any]:
    parent = "checkout.orders:submit_order"
    return from_contracts(
        codebase="checkout-demo",
        revision="synthetic-v1",
        service="checkout-service",
        contracts=DEMO_CONTRACTS,
        dependencies=[(parent, path) for path in DEMO_CONTRACTS if path != parent],
    )


def reconcile_settlement(authorized: int, orders: int) -> bool:
    """Declared demo boundary intentionally unexercised by the checkout scenario."""
    return authorized == orders


def generate(provider: TracerProvider, count: int = 24) -> dict[str, Any]:
    tracer: Tracer = provider.get_tracer("melampus.demo", "0.1.0")

    @instrumented(
        intent=DEMO_CONTRACTS["checkout.pricing:calculate_total"].intent,
        checks=DEMO_CONTRACTS["checkout.pricing:calculate_total"].checks,
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.pricing:calculate_total",
    )
    def price(discount: float) -> float:
        time.sleep(0.002)
        return 100 * (1 - discount)

    @instrumented(
        intent=DEMO_CONTRACTS["checkout.inventory:reserve_stock"].intent,
        checks=DEMO_CONTRACTS["checkout.inventory:reserve_stock"].checks,
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.inventory:reserve_stock",
    )
    def reserve(quantity: int) -> int:
        time.sleep(0.001)
        return quantity

    @instrumented(
        intent=DEMO_CONTRACTS["checkout.payments:authorize"].intent,
        checks=DEMO_CONTRACTS["checkout.payments:authorize"].checks,
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
        intent=DEMO_CONTRACTS["checkout.shipping:calculate_shipping"].intent,
        checks=DEMO_CONTRACTS["checkout.shipping:calculate_shipping"].checks,
        policy=Policy(checks_per_second=0),
        tracer=tracer,
        generator="synthetic-demo",
        path="checkout.shipping:calculate_shipping",
    )
    def shipping() -> int:
        return 5

    @instrumented(
        intent=DEMO_CONTRACTS["checkout.orders:submit_order"].intent,
        checks=DEMO_CONTRACTS["checkout.orders:submit_order"].checks,
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
