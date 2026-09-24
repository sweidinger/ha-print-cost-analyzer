"""Print job tracking: follows each printer, snapshots at start, settles at end."""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_STATES, EVENT_JOB_FINISHED, IMAGE_DIR, IMAGE_URL, RESULT_FAILED,
    RESULT_FINISHED, SIGNAL_UPDATED, STORAGE_KEY, STORAGE_VERSION, UID_COVER,
    UID_GCODE, UID_START, UID_STATUS, UID_TASK, UID_WEIGHT,
)
from .costs import price_per_gram, spool_usage, summarize, to_kwh

_LOGGER = logging.getLogger(__name__)
_SPOOL_RE = re.compile(r"^sensor\.spoolman_spool_(\d+)$")
_MAKERWORLD_RE = re.compile(r"^(\d{4,})-")


class Printer:
    """One tracked printer, resolved from its ha-bambulab print-status entity."""

    def __init__(self, hass: HomeAssistant, status_entity: str,
                 energy_entity: str | None) -> None:
        self.status_entity = status_entity
        self.energy_entity = energy_entity
        self.serial = ""
        self.name = status_entity
        self.device_id: str | None = None
        self.siblings: dict[str, str] = {}
        ent_reg = er.async_get(hass)
        entry = ent_reg.async_get(status_entity)
        if entry and entry.unique_id.endswith(UID_STATUS):
            self.serial = entry.unique_id[: -len(UID_STATUS)]
            self.device_id = entry.device_id
            for suffix in (UID_TASK, UID_GCODE, UID_WEIGHT, UID_START, UID_COVER):
                domain = "image" if suffix == UID_COVER else "sensor"
                eid = ent_reg.async_get_entity_id(domain, entry.platform,
                                                  self.serial + suffix)
                if eid:
                    self.siblings[suffix] = eid
            device = dr.async_get(hass).async_get(entry.device_id) if entry.device_id else None
            if device:
                self.name = _clean_name(device.name_by_user or device.name, self.serial)
        self._device_entities = [
            e.entity_id for e in er.async_entries_for_device(ent_reg, self.device_id)
        ] if self.device_id else []

    def sibling_state(self, hass: HomeAssistant, suffix: str) -> str | None:
        eid = self.siblings.get(suffix)
        st = hass.states.get(eid) if eid else None
        if st is None or st.state in ("unknown", "unavailable", ""):
            return None
        return st.state

    def tray_tags(self, hass: HomeAssistant) -> set[str]:
        """Bambu spool ids currently loaded in this printer's AMS/external slots."""
        tags: set[str] = set()
        for eid in self._device_entities:
            st = hass.states.get(eid)
            if st is None:
                continue
            tag = st.attributes.get("tray_uuid")
            if tag and tag.strip("0"):
                tags.add(str(tag).upper())
        return tags


class PrintTracker:
    """Owns the job store and all printer listeners of one config entry."""

    def __init__(self, hass: HomeAssistant, printers: list[Printer],
                 price_entity: str, settle_minutes: int) -> None:
        self.hass = hass
        self.printers = {p.status_entity: p for p in printers}
        self.price_entity = price_entity
        self.settle = timedelta(minutes=max(0, settle_minutes))
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.jobs: list[dict[str, Any]] = []
        self.active: dict[str, dict[str, Any]] = {}
        self._unsubs: list = []
        self._timers: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------
    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.jobs = data.get("jobs", [])
        self.active = data.get("active", {})
        await self.hass.async_add_executor_job(
            os.makedirs, self.hass.config.path(IMAGE_DIR), 0o755, True)
        self._unsubs.append(async_track_state_change_event(
            self.hass, list(self.printers), self._on_status))
        self._meta_owner = {
            p.siblings[k]: eid for eid, p in self.printers.items()
            for k in (UID_TASK, UID_GCODE, UID_WEIGHT, UID_START) if k in p.siblings
        }
        if self._meta_owner:
            self._unsubs.append(async_track_state_change_event(
                self.hass, list(self._meta_owner), self._on_meta))
        # Repair jobs that were taken for fresh starts although the printer
        # reports an earlier start (2.0.0/2.0.1 after a lost connection).
        for eid, job in self.active.items():
            printer = self.printers.get(eid)
            if printer is None or job.get("partial") or job.get("ended_at"):
                continue
            raw = printer.sibling_state(self.hass, UID_START)
            real = dt_util.parse_datetime(raw) if raw else None
            noted = dt_util.parse_datetime(job["started_at"])
            if real and noted and noted - real > timedelta(minutes=10):
                job["started_at"] = real.isoformat()
                job["partial"] = True
                _LOGGER.info("%s: start corrected to %s (missed start)", printer.name, real)
        for eid, job in self.active.items():
            if eid in self.printers and not job.get("ended_at"):
                self._refresh_meta(self.printers[eid], job)
        # Reconcile what happened while Home Assistant was not running.
        for eid, printer in self.printers.items():
            st = self.hass.states.get(eid)
            state = st.state if st else None
            job = self.active.get(eid)
            if job and job.get("ended_at"):
                self._schedule_settle(eid, immediate=True)
            elif job and state not in ACTIVE_STATES and state not in (None, "unavailable", "unknown"):
                await self._end(printer, state or "unknown")
            elif not job and state in ACTIVE_STATES:
                await self._begin(printer, partial=True)

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        for cancel in self._timers.values():
            cancel()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({"jobs": self.jobs, "active": self.active})

    # -- state machine -----------------------------------------------------
    @callback
    def _on_status(self, event: Event) -> None:
        eid = event.data["entity_id"]
        new: State | None = event.data.get("new_state")
        old: State | None = event.data.get("old_state")
        printer = self.printers.get(eid)
        if printer is None or new is None:
            return
        was = old.state if old else None
        now = new.state
        job = self.active.get(eid)
        if now in ACTIVE_STATES and not job:
            # Coming back from unavailable/unknown (restart, lost connection)
            # means the print was already running: take the printer's own
            # start time and mark the job as partially observed.
            missed = was in (None, "unavailable", "unknown")
            self.hass.async_create_task(self._begin(printer, partial=missed))
        elif job and not job.get("ended_at") and now not in ACTIVE_STATES \
                and now not in ("unavailable", "unknown") and was in ACTIVE_STATES:
            self.hass.async_create_task(self._end(printer, now))

    @callback
    def _on_meta(self, event: Event) -> None:
        """Task name, file, weight or start time arrived after the status did."""
        eid = self._meta_owner.get(event.data["entity_id"])
        job = self.active.get(eid) if eid else None
        if job and not job.get("ended_at") and self._refresh_meta(self.printers[eid], job):
            self.hass.async_create_task(self._save())
            async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def _refresh_meta(self, printer: Printer, job: dict[str, Any]) -> bool:
        """Fill in what was unknown when the job began. True if anything changed.

        After a restart or a lost connection the print status often comes back
        a moment before the task name and start time do.
        """
        changed = False
        task = printer.sibling_state(self.hass, UID_TASK)
        gcode = printer.sibling_state(self.hass, UID_GCODE)
        if task and job.get("name") in (None, "", "Druck", job.get("file")):
            job["name"] = task
            changed = True
        if gcode and not job.get("file"):
            job["file"] = gcode
            mw = _MAKERWORLD_RE.match(gcode)
            job["makerworld_id"] = mw.group(1) if mw else None
            if job.get("name") in (None, "", "Druck"):
                job["name"] = gcode
            changed = True
        weight = _float(printer.sibling_state(self.hass, UID_WEIGHT))
        if weight and not job.get("planned_grams"):
            job["planned_grams"] = weight
            changed = True
        if job.get("partial"):
            raw = printer.sibling_state(self.hass, UID_START)
            real = dt_util.parse_datetime(raw) if raw else None
            noted = dt_util.parse_datetime(job["started_at"])
            if real and noted and real < noted:
                job["started_at"] = real.isoformat()
                changed = True
        return changed

    async def _begin(self, printer: Printer, partial: bool = False) -> None:
        hass = self.hass
        start_raw = printer.sibling_state(hass, UID_START)
        # The printer's own start time is only trusted when we missed the start
        # (HA was down): at a live start it may still show the previous print.
        parsed = dt_util.parse_datetime(start_raw) if start_raw else None
        started = parsed if (partial and parsed) else dt_util.utcnow()
        gcode = printer.sibling_state(hass, UID_GCODE) or ""
        mw = _MAKERWORLD_RE.match(gcode)
        job = {
            "id": uuid.uuid4().hex[:12],
            "printer": printer.name,
            "printer_entity": printer.status_entity,
            "serial": printer.serial,
            "name": printer.sibling_state(hass, UID_TASK) or gcode or "Druck",
            "file": gcode,
            "makerworld_id": mw.group(1) if mw else None,
            "started_at": started.isoformat(),
            "planned_grams": _float(printer.sibling_state(hass, UID_WEIGHT)),
            "energy_start": self._energy(printer),
            "spools_start": self._spool_snapshot(printer),
            "tags_seen": sorted(printer.tray_tags(hass)),
            "partial": partial,
        }
        self.active[printer.status_entity] = job
        _LOGGER.info("%s: print started - %s", printer.name, job["name"])
        await self._save()
        async_dispatcher_send(hass, SIGNAL_UPDATED)

    async def _end(self, printer: Printer, state: str) -> None:
        job = self.active.get(printer.status_entity)
        if not job or job.get("ended_at"):
            return
        self._refresh_meta(printer, job)
        job["ended_at"] = dt_util.utcnow().isoformat()
        job["result"] = ("finished" if state == RESULT_FINISHED
                         else "failed" if state == RESULT_FAILED else "cancelled")
        job["energy_end"] = self._energy(printer)
        job["image"] = await self._save_cover(printer, job["id"])
        await self._save()
        self._schedule_settle(printer.status_entity)

    def _schedule_settle(self, eid: str, immediate: bool = False) -> None:
        if eid in self._timers:
            self._timers.pop(eid)()
        delay = 0 if immediate else self.settle.total_seconds()
        if delay <= 0:
            self.hass.async_create_task(self._settle(eid))
            return

        @callback
        def _fire(_now: datetime) -> None:
            self._timers.pop(eid, None)
            self.hass.async_create_task(self._settle(eid))

        self._timers[eid] = async_call_later(self.hass, delay, _fire)

    async def _settle(self, eid: str) -> None:
        """Book the finished job once OpenSpoolMan/Spoolman have caught up."""
        job = self.active.pop(eid, None)
        printer = self.printers.get(eid)
        if not job or printer is None:
            return
        after = self._spool_snapshot(printer, extra=job["spools_start"])
        used = spool_usage(
            {k: v["used"] for k, v in job["spools_start"].items()},
            {k: v["used"] for k, v in after.items()},
        )
        filaments = []
        for sid, grams in used.items():
            meta = after.get(sid) or job["spools_start"][sid]
            ppg = meta.get("ppg")
            filaments.append({
                "spool_id": int(sid), "name": meta.get("name"), "color": meta.get("color"),
                "material": meta.get("material"), "grams": grams,
                "price_per_g": round(ppg, 5) if ppg else None,
                "cost": round(grams * ppg, 4) if ppg else None,
            })
        source = "spoolman"
        if not filaments and job.get("planned_grams") and job["result"] == "finished":
            # Nothing was booked to Spoolman - fall back to the slicer's estimate,
            # priced with the spool that was loaded when the print began.
            source = "slicer"
            grams = job["planned_grams"]
            meta = next((m for m in job["spools_start"].values()
                         if m.get("tag") in job.get("tags_seen", [])), None)
            ppg = meta.get("ppg") if meta else None
            filaments.append({
                "spool_id": int(meta["id"]) if meta else None,
                "name": meta.get("name") if meta else "laut Slicer",
                "color": meta.get("color") if meta else None,
                "material": meta.get("material") if meta else None,
                "grams": grams, "price_per_g": ppg,
                "cost": round(grams * ppg, 4) if ppg else None,
            })
        e0, e1 = job.get("energy_start"), job.get("energy_end")
        energy = round(e1 - e0, 4) if e0 is not None and e1 is not None and e1 >= e0 else None
        price = _float(_state(self.hass, self.price_entity))
        started = dt_util.parse_datetime(job["started_at"])
        ended = dt_util.parse_datetime(job["ended_at"])
        record = {
            k: job.get(k) for k in ("id", "printer", "printer_entity", "serial", "name",
                                    "file", "makerworld_id", "started_at", "ended_at",
                                    "result", "planned_grams", "image", "partial")
        }
        record["printer"] = printer.name
        record.update({
            "duration_s": int((ended - started).total_seconds()) if started and ended else None,
            "energy_kwh": energy,
            "energy_price": price,
            "filaments": filaments,
            "filament_source": source if filaments else None,
            **summarize(energy, price, filaments),
        })
        self.jobs.append(record)
        await self._save()
        _LOGGER.info("%s: print booked - %s, %.2f EUR", printer.name,
                     record["name"], record["total_cost"] or 0)
        self.hass.bus.async_fire(EVENT_JOB_FINISHED, record)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    # -- data sources ------------------------------------------------------
    def _energy(self, printer: Printer) -> float | None:
        if not printer.energy_entity:
            return None
        st = self.hass.states.get(printer.energy_entity)
        val = _float(st.state) if st else None
        return to_kwh(val, st.attributes.get("unit_of_measurement")) if val is not None else None

    def _spool_snapshot(self, printer: Printer,
                        extra: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        """Spoolman spools belonging to this printer, keyed by spool id."""
        tags = printer.tray_tags(self.hass)
        keep = set(extra or {})
        out: dict[str, dict[str, Any]] = {}
        for st in self.hass.states.async_all("sensor"):
            m = _SPOOL_RE.match(st.entity_id)
            if not m:
                continue
            a = st.attributes
            sid = m.group(1)
            tray = str(a.get("extra_active_tray") or "").strip('"')
            tag = str(a.get("extra_tag") or "").strip('"').upper()
            mine = (printer.serial and tray.startswith(printer.serial + "_")) or (tag and tag in tags)
            if not mine and sid not in keep:
                continue
            used = _float(a.get("used_weight"))
            if used is None:
                continue
            out[sid] = {
                "id": sid, "used": used, "tag": tag,
                "name": " ".join(x for x in (a.get("filament_vendor_name"),
                                              a.get("filament_material"),
                                              a.get("filament_name")) if x) or a.get("friendly_name"),
                "material": a.get("filament_material"),
                "color": a.get("filament_color_hex") or (a.get("filament_multi_color_hexes") or "").split(",")[0] or None,
                "ppg": price_per_gram(dict(a)),
            }
        return out

    async def _save_cover(self, printer: Printer, job_id: str) -> str | None:
        eid = printer.siblings.get(UID_COVER)
        if not eid:
            return None
        try:
            from homeassistant.components.image import DATA_COMPONENT
            entity = self.hass.data[DATA_COMPONENT].get_entity(eid)
            if entity is None:
                return None
            data = await entity.async_image()
            if not data:
                return None
            ext = "png" if data[:4] == b"\x89PNG" else "jpg"
            path = self.hass.config.path(IMAGE_DIR, f"{job_id}.{ext}")
            await self.hass.async_add_executor_job(_write, path, data)
            return f"{IMAGE_URL}/{job_id}.{ext}"
        except Exception as err:  # noqa: BLE001 - a missing picture never blocks a job
            _LOGGER.debug("%s: cover image not saved: %s", printer.name, err)
            return None

    # -- maintenance -------------------------------------------------------
    async def async_delete(self, job_id: str) -> bool:
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.get("id") != job_id]
        if len(self.jobs) == before:
            return False
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return True


def _clean_name(name: str | None, serial: str) -> str:
    """'H2D_0948BB520500417' -> 'H2D': ha-bambulab appends the serial to device names."""
    if not name:
        return serial
    if serial:
        for sep in ("_", " ", "-", ""):
            suffix = f"{sep}{serial}"
            if name.upper().endswith(suffix.upper()) and len(name) > len(suffix):
                return name[: -len(suffix)].strip() or name
    return name


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


def _state(hass: HomeAssistant, eid: str | None) -> str | None:
    st = hass.states.get(eid) if eid else None
    return st.state if st else None


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "unknown", "unavailable"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
