"""3D Print Cost Analyzer - cost of every print from Bambu Lab, Spoolman and a power meter."""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback

from .const import (
    CARD_URL, CONF_ENERGY, CONF_PRICE_ENTITY, CONF_PRINTERS, CONF_SETTLE_MINUTES,
    DEFAULT_PRICE_ENTITY, DEFAULT_SETTLE_MINUTES, DOMAIN,
)
from .tracker import Printer, PrintTracker

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CSV_FIELDS = ["id", "started_at", "ended_at", "duration_s", "printer", "name", "result",
              "energy_kwh", "energy_price", "energy_cost", "filament_grams",
              "filament_cost", "total_cost", "filament_source", "spools"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the dashboard card and register the websocket command once."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / "print-cost-card.js"), False)
    ])
    add_extra_js_url(hass, f"{CARD_URL}?v=2.0.0")
    websocket_api.async_register_command(hass, ws_jobs)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    opts = {**entry.data, **entry.options}
    energy = opts.get(CONF_ENERGY, {})
    printers = [Printer(hass, eid, energy.get(eid)) for eid in opts.get(CONF_PRINTERS, [])]
    tracker = PrintTracker(
        hass, printers,
        opts.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY),
        int(opts.get(CONF_SETTLE_MINUTES, DEFAULT_SETTLE_MINUTES)),
    )
    await tracker.async_start()
    entry.runtime_data = tracker
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = tracker
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    tracker: PrintTracker = hass.data[DOMAIN].pop(entry.entry_id)
    await tracker.async_stop()
    return ok


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _tracker(hass: HomeAssistant) -> PrintTracker | None:
    trackers = list(hass.data.get(DOMAIN, {}).values())
    return trackers[0] if trackers else None


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "export_csv"):
        return

    async def export_csv(call: ServiceCall) -> ServiceResponse:
        tracker = _tracker(hass)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for job in tracker.jobs if tracker else []:
            row = dict(job)
            row["spools"] = " | ".join(
                f"{f.get('name')}: {f.get('grams')} g" for f in job.get("filaments", []))
            writer.writerow(row)
        path = hass.config.path("print_cost_analyzer.csv")
        await hass.async_add_executor_job(Path(path).write_text, buf.getvalue(), "utf-8")
        return {"path": path, "prints": len(tracker.jobs) if tracker else 0}

    async def delete_job(call: ServiceCall) -> None:
        tracker = _tracker(hass)
        if tracker:
            await tracker.async_delete(call.data["job_id"])

    hass.services.async_register(DOMAIN, "export_csv", export_csv,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "delete_job", delete_job,
                                 schema=vol.Schema({vol.Required("job_id"): str}))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/jobs"})
@callback
def ws_jobs(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """All booked prints (newest first) and the ones still running."""
    tracker = _tracker(hass)
    if tracker is None:
        connection.send_result(msg["id"], {"jobs": [], "active": [], "printers": []})
        return
    active = [
        {k: v for k, v in job.items() if k not in ("spools_start", "tags_seen")}
        for job in tracker.active.values()
    ]
    connection.send_result(msg["id"], {
        "jobs": list(reversed(tracker.jobs)),
        "active": active,
        "printers": sorted({p.name for p in tracker.printers.values()}),
    })
