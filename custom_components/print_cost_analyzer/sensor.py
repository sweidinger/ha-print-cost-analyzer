"""Summary sensors for the 3D Print Cost Analyzer."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_UPDATED
from .tracker import PrintTracker


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    tracker: PrintTracker = entry.runtime_data
    async_add_entities([
        CostSensor(tracker, entry, "total", "Druckkosten gesamt"),
        CostSensor(tracker, entry, "month", "Druckkosten diesen Monat"),
        CountSensor(tracker, entry),
        LastPrintSensor(tracker, entry),
        IdleCostSensor(tracker, entry, "total", "Leerlaufkosten gesamt"),
        IdleCostSensor(tracker, entry, "month", "Leerlaufkosten diesen Monat"),
    ])


class _Base(SensorEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, tracker: PrintTracker, entry: ConfigEntry, key: str, name: str) -> None:
        self.tracker = tracker
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


class CostSensor(_Base):
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, tracker, entry, period: str, name: str) -> None:
        super().__init__(tracker, entry, f"cost_{period}", name)
        self.period = period
        self._attr_state_class = (SensorStateClass.TOTAL if period == "month"
                                  else SensorStateClass.TOTAL_INCREASING)

    def _jobs(self):
        if self.period == "total":
            return self.tracker.jobs
        month = dt_util.now().strftime("%Y-%m")
        return [j for j in self.tracker.jobs
                if dt_util.as_local(dt_util.parse_datetime(j["started_at"])).strftime("%Y-%m") == month]

    @property
    def native_value(self) -> float:
        return round(sum(j.get("total_cost") or 0 for j in self._jobs()), 2)

    @property
    def extra_state_attributes(self):
        jobs = self._jobs()
        return {
            "prints": len(jobs),
            "energy_cost": round(sum(j.get("energy_cost") or 0 for j in jobs), 2),
            "filament_cost": round(sum(j.get("filament_cost") or 0 for j in jobs), 2),
            "energy_kwh": round(sum(j.get("energy_kwh") or 0 for j in jobs), 3),
            "filament_grams": round(sum(j.get("filament_grams") or 0 for j in jobs), 1),
        }


def _this_month(records):
    month = dt_util.now().strftime("%Y-%m")
    return [r for r in records
            if dt_util.as_local(dt_util.parse_datetime(r["started_at"])).strftime("%Y-%m") == month]


class IdleCostSensor(_Base):
    """Electricity the printers drew while switched on without printing."""

    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:power-sleep"

    def __init__(self, tracker, entry, period: str, name: str) -> None:
        super().__init__(tracker, entry, f"idle_cost_{period}", name)
        self.period = period
        self._attr_state_class = (SensorStateClass.TOTAL if period == "month"
                                  else SensorStateClass.TOTAL_INCREASING)

    def _phases(self):
        return self.tracker.idle if self.period == "total" else _this_month(self.tracker.idle)

    @property
    def native_value(self) -> float:
        return round(sum(r.get("energy_cost") or 0 for r in self._phases()), 2)

    @property
    def extra_state_attributes(self):
        phases = self._phases()
        per_printer: dict[str, float] = {}
        for r in phases:
            per_printer[r.get("printer")] = round(
                per_printer.get(r.get("printer"), 0) + (r.get("energy_cost") or 0), 4)
        return {
            "phases": len(phases),
            "energy_kwh": round(sum(r.get("energy_kwh") or 0 for r in phases), 3),
            "hours": round(sum(r.get("duration_s") or 0 for r in phases) / 3600, 1),
            "per_printer": per_printer,
            "idle_now": [r["printer"] for r in self.tracker.idle_running()],
        }


class CountSensor(_Base):
    _attr_icon = "mdi:printer-3d"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "Drucke"

    def __init__(self, tracker, entry) -> None:
        super().__init__(tracker, entry, "count", "Anzahl Drucke")

    @property
    def native_value(self) -> int:
        return len(self.tracker.jobs)

    @property
    def extra_state_attributes(self):
        return {"running": [
            (self.tracker.printers[eid].name if eid in self.tracker.printers else j.get("printer"))
            for eid, j in self.tracker.active.items() if not j.get("ended_at")]}


class LastPrintSensor(_Base):
    _attr_icon = "mdi:receipt-text"
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _unrecorded_attributes = frozenset({"filaments"})

    def __init__(self, tracker, entry) -> None:
        super().__init__(tracker, entry, "last", "Letzter Druck")

    @property
    def native_value(self):
        return self.tracker.jobs[-1].get("total_cost") if self.tracker.jobs else None

    @property
    def extra_state_attributes(self):
        if not self.tracker.jobs:
            return None
        j = self.tracker.jobs[-1]
        return {k: j.get(k) for k in ("name", "printer", "started_at", "ended_at", "duration_s",
                                      "result", "energy_kwh", "energy_cost", "filament_grams",
                                      "filament_cost", "filaments", "image")}
