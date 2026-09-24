from custom_components.print_cost_analyzer.costs import price_per_gram, spool_usage, summarize, to_kwh


def test_to_kwh():
    assert to_kwh(1500, "Wh") == 1.5
    assert to_kwh(1.5, "kWh") == 1.5


def test_price_per_gram_prefers_spool_then_filament():
    assert price_per_gram({"price": 25.0, "initial_weight": 1000}) == 0.025
    assert price_per_gram({"filament_price": 20.0, "filament_weight": 1000}) == 0.02
    assert price_per_gram({"price": 0, "filament_price": 20.0, "filament_weight": 500}) == 0.04
    assert price_per_gram({"initial_weight": 1000}) is None


def test_spool_usage_uses_used_weight_and_ignores_noise():
    before = {"1": 100.0, "2": 50.0, "3": 10.0}
    after = {"1": 112.5, "2": 50.01, "3": 10.0}
    assert spool_usage(before, after) == {"1": 12.5}


def test_summarize_adds_energy_and_filament():
    out = summarize(0.5, 0.3, [{"grams": 10, "cost": 0.25}, {"grams": 5, "cost": 0.1}])
    assert out["energy_cost"] == 0.15
    assert out["filament_cost"] == 0.35
    assert out["total_cost"] == 0.5
    assert out["filament_grams"] == 15
    assert out["missing_price"] is False


def test_summarize_flags_missing_price():
    out = summarize(0.5, 0.3, [{"grams": 10, "cost": None}])
    assert out["missing_price"] is True
    assert out["filament_cost"] is None
    assert out["total_cost"] == 0.15
