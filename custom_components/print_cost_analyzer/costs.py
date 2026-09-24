"""Pure cost helpers - kept free of Home Assistant so they are easy to test."""
from __future__ import annotations

from typing import Any


def to_kwh(value: float, unit: str | None) -> float:
    """Normalise an energy reading to kWh."""
    unit = (unit or "kWh").strip()
    if unit == "Wh":
        return value / 1000
    if unit == "MWh":
        return value * 1000
    return value


def price_per_gram(attrs: dict[str, Any]) -> float | None:
    """EUR per gram of a Spoolman spool: spool price first, else filament price."""
    for price_key, weight_keys in (
        ("price", ("initial_weight", "filament_weight")),
        ("filament_price", ("filament_weight", "initial_weight")),
    ):
        price = _num(attrs.get(price_key))
        if price is None or price <= 0:
            continue
        for wk in weight_keys:
            weight = _num(attrs.get(wk))
            if weight and weight > 0:
                return price / weight
    return None


def spool_usage(before: dict[str, float], after: dict[str, float],
                min_grams: float = 0.05) -> dict[str, float]:
    """Grams used per spool between two snapshots of Spoolman's used_weight.

    used_weight only grows, unlike remaining_weight, which Spoolman clamps at
    zero - a spool that was booked past empty would otherwise look unused.
    """
    out: dict[str, float] = {}
    for sid, start in before.items():
        end = after.get(sid)
        if end is None:
            continue
        delta = end - start
        if delta >= min_grams:
            out[sid] = round(delta, 2)
    return out


def summarize(energy_kwh: float | None, price_kwh: float | None,
              filaments: list[dict[str, Any]]) -> dict[str, Any]:
    """Energy cost, filament cost and total for one print."""
    energy_cost = (round(energy_kwh * price_kwh, 4)
                   if energy_kwh is not None and price_kwh is not None else None)
    priced = [f["cost"] for f in filaments if f.get("cost") is not None]
    filament_cost = round(sum(priced), 4) if priced else (0.0 if not filaments else None)
    missing_price = any(f.get("cost") is None for f in filaments)
    parts = [c for c in (energy_cost, filament_cost) if c is not None]
    return {
        "energy_cost": energy_cost,
        "filament_cost": filament_cost,
        "total_cost": round(sum(parts), 4) if parts else None,
        "filament_grams": round(sum(f.get("grams", 0) for f in filaments), 2),
        "missing_price": missing_price,
    }


def _num(value: Any) -> float | None:
    try:
        if value in (None, "", "unknown", "unavailable"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
