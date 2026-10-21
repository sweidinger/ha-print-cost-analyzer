"""Print job tracking: follows each printer, snapshots at start, settles at end.

Between prints it also records idle phases: the time a printer is switched on
without printing, with the energy it drew meanwhile.
"""
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
    ACTIVE_STATES, EVENT_JOB_FINISHED, IDLE_MIN_SECONDS, IDLE_RESUME_MINUTES, IMAGE_DIR,
    IMAGE_URL, OFF_STATES, PREP_STATES, RESULT_FAILED, RESULT_FINISHED, SIGNAL_UPDATED,
    STORAGE_KEY, STORAGE_VERSION, UID_ACTIVE_TRAY, UID_COVER, UID_GCODE, UID_START,
    UID_STATUS, UID_TASK, UID_WEIGHT,
)
from .costs import (
    price_per_gram, split_grams, spool_usage, spoolman_plausible, summarize, to_kwh,
)

_LOGGER = logging.getLogger(__name__)
_SPOOL_RE = re.compile(r"^sensor\.spoolman_spool_(\d+)$")


def _stem(name: str | None) -> str:
    """Vergleichbarer Kern eines Auftrags-/Dateinamens: ha-bambulab stellt dem
    heruntergeladenen G-Code die Dateigröße voran („21863866-Name.gcode“)."""
    s = (name or "").lower()
    s = re.sub(r"^\d+-", "", s)
    s = re.sub(r"(\.gcode)?(\.3mf)?$", "", s)
    s = re.sub(r"_plate_\d+$", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _meta_current(task: str | None, gcode: str | None) -> bool:
    """Gehört der zuletzt heruntergeladene G-Code (samt Gewicht und Titelbild) zum
    laufenden Auftrag? Startet der Druck aus dem SD-Wurzelverzeichnis (\"Senden\",
    Druckstart aus HA), lädt ha-bambulab das Modell nicht nach und die Sensoren
    zeigen noch den vorherigen Druck."""
    a, b = _stem(task), _stem(gcode)
    if not a or not b:
        return True
    return a in b or b in a


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
            for suffix in (UID_TASK, UID_GCODE, UID_WEIGHT, UID_START, UID_COVER,
                           UID_ACTIVE_TRAY):
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

    def active_tray(self, hass: HomeAssistant) -> tuple[str, str] | None:
        """(tag, 'SERIAL_ams_tray') of the tray feeding the nozzle right now."""
        eid = self.siblings.get(UID_ACTIVE_TRAY)
        st = hass.states.get(eid) if eid else None
        if st is None or st.state.lower() in ("", "none", "empty", "unknown", "unavailable"):
            return None
        a = st.attributes
        tag = str(a.get("tray_uuid") or "").upper()
        tag = tag if tag.strip("0") else ""
        ams, tray = a.get("ams_index"), a.get("tray_index")
        slot = f"{self.serial}_{ams}_{tray}" if self.serial and ams is not None \
            and tray is not None else ""
        return (tag, slot) if tag or slot else None


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
        self.idle: list[dict[str, Any]] = []
        self.idle_active: dict[str, dict[str, Any]] = {}
        self._unsubs: list = []
        self._timers: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------
    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.jobs = data.get("jobs", [])
        self.active = data.get("active", {})
        self.idle = data.get("idle", [])
        self.idle_active = data.get("idle_active", {})
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
        self._tray_owner = {
            p.siblings[UID_ACTIVE_TRAY]: eid for eid, p in self.printers.items()
            if UID_ACTIVE_TRAY in p.siblings
        }
        if self._tray_owner:
            self._unsubs.append(async_track_state_change_event(
                self.hass, list(self._tray_owner), self._on_tray))
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
                self._note_tray(self.printers[eid], job)
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
        # Idle phases: one that was open is closed if the printer is off now;
        # a printer that is on and not printing gets one (start time unknown).
        for eid, printer in self.printers.items():
            state = _state(self.hass, eid)
            if eid in self.idle_active and state in OFF_STATES:
                await self._close_idle(printer, "off", partial=True)
            elif eid not in self.idle_active and eid not in self.active \
                    and state not in ACTIVE_STATES and state not in OFF_STATES \
                    and state not in (None, "unknown"):
                await self._open_idle(printer, partial=True)

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        for cancel in self._timers.values():
            cancel()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({"jobs": self.jobs, "active": self.active,
                                      "idle": self.idle, "idle_active": self.idle_active})

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
        open_job = job if job and not job.get("ended_at") else None
        offline_since = open_job.get("offline_since") if open_job else None
        if open_job and offline_since and now in ACTIVE_STATES:
            if self._same_task(printer, open_job):
                # Back after an interruption (Wi-Fi, MQTT, power): the print goes on.
                self._resume(printer, open_job)
            else:
                # A different print started: the interrupted one never resumed.
                self.hass.async_create_task(self._replace_interrupted(printer, open_job))
                return
        if now in ACTIVE_STATES and not job:
            # Coming back from unavailable/unknown (restart, lost connection)
            # means the print was already running: take the printer's own
            # start time and mark the job as partially observed.
            missed = was in (None, "unavailable", "unknown")
            self.hass.async_create_task(self._begin(printer, partial=missed))
        elif open_job and now == "offline":
            # Offline during a print: Wi-Fi, MQTT broker or power. The printer
            # may resume when it is back, so the job stays open ("unterbrochen")
            # for as long as it takes - no timeout.
            if not offline_since:
                self._interrupt(printer, open_job)
        elif open_job and offline_since and now not in ACTIVE_STATES \
                and now not in (RESULT_FINISHED, RESULT_FAILED):
            # Back but not printing (e.g. idle with "resume print?" after a power
            # cut), or offline/unavailable again: stays interrupted. It ends as
            # cancelled only when a different print starts.
            pass
        elif job and not job.get("ended_at") and now not in ACTIVE_STATES \
                and now not in OFF_STATES and now != "unknown":
            # Also from unavailable: a printer that finished while it was
            # unreachable comes back straight as 'finish'.
            self.hass.async_create_task(self._end(printer, now))
        elif job and not job.get("ended_at") and self._note_tray(printer, job):
            self.hass.async_create_task(self._save())
        # Idle phases. A print's start and end open and close them in _begin/_end;
        # here: the printer is switched off, or switched on without printing.
        if now in OFF_STATES and eid in self.idle_active:
            self.hass.async_create_task(self._close_idle(printer, "off"))
        elif (not job or job.get("ended_at")) and eid not in self.idle_active \
                and now not in ACTIVE_STATES \
                and now not in OFF_STATES and now != "unknown":
            self.hass.async_create_task(self._open_idle(printer, resume=was in OFF_STATES))

    @callback
    def _on_tray(self, event: Event) -> None:
        """Another AMS tray feeds the nozzle: remember it as used by the job."""
        eid = self._tray_owner.get(event.data["entity_id"])
        job = self.active.get(eid) if eid else None
        if job and not job.get("ended_at") and self._note_tray(self.printers[eid], job):
            self.hass.async_create_task(self._save())

    def _note_tray(self, printer: Printer, job: dict[str, Any]) -> bool:
        """Add the active tray to the job's used trays. True if it was new."""
        if job.get("ended_at") or _state(self.hass, printer.status_entity) in PREP_STATES:
            return False
        active = printer.active_tray(self.hass)
        if active is None:
            return False
        changed = False
        for key, value in zip(("used_tags", "used_trays"), active):
            seen = job.setdefault(key, [])
            if value and value not in seen:
                seen.append(value)
                changed = True
        return changed

    @callback
    def _on_meta(self, event: Event) -> None:
        """Task name, file, weight or start time arrived after the status did."""
        eid = self._meta_owner.get(event.data["entity_id"])
        job = self.active.get(eid) if eid else None
        if job and not job.get("ended_at") and self._refresh_meta(self.printers[eid], job):
            self.hass.async_create_task(self._save())
            async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def _refresh_meta(self, printer: Printer, job: dict[str, Any],
                      at_end: bool = False) -> bool:
        """Fill in what was unknown when the job began. True if anything changed.

        After a restart or a lost connection the print status often comes back
        a moment before the task name and start time do.
        """
        changed = False
        task = printer.sibling_state(self.hass, UID_TASK)
        gcode = printer.sibling_state(self.hass, UID_GCODE)
        current = _meta_current(task or job.get("name"), gcode)
        if not current:
            gcode = None
        if task and job.get("name") in (None, "", "Druck", job.get("file")):
            job["name"] = task
            changed = True
        if gcode and not job.get("file"):
            job["file"] = gcode
            if job.get("name") in (None, "", "Druck"):
                job["name"] = gcode
            changed = True
        weight = _float(printer.sibling_state(self.hass, UID_WEIGHT)) if current else None
        if weight and not job.get("planned_grams"):
            job["planned_grams"] = weight
            changed = True
        raw = printer.sibling_state(self.hass, UID_START)
        real = dt_util.parse_datetime(raw) if raw else None
        noted = dt_util.parse_datetime(job["started_at"])
        if real and noted and real < noted:
            # While a job is partial the printer's start time is trusted. At the
            # end of a print it always belongs to that print, so a start noted
            # much later than the printer's own is corrected then as well.
            if job.get("partial") or (at_end and noted - real > timedelta(minutes=10)):
                job["started_at"] = real.isoformat()
                job["partial"] = True
                changed = True
        if job.get("energy_start") is None and printer.energy_entity and not at_end:
            # The meter was unavailable when the job began: count from now on.
            reading = self._energy(printer)
            if reading is not None:
                job["energy_start"] = reading
                job["partial"] = True
                changed = True
        return changed

    async def _begin(self, printer: Printer, partial: bool = False) -> None:
        hass = self.hass
        await self._close_idle(printer, "print")
        start_raw = printer.sibling_state(hass, UID_START)
        # The printer's own start time is only trusted when we missed the start
        # (HA was down): at a live start it may still show the previous print.
        parsed = dt_util.parse_datetime(start_raw) if start_raw else None
        started = parsed if (partial and parsed) else dt_util.utcnow()
        gcode = printer.sibling_state(hass, UID_GCODE) or ""
        task = printer.sibling_state(hass, UID_TASK)
        current = _meta_current(task, gcode)
        if not current:
            gcode = ""
        job = {
            "id": uuid.uuid4().hex[:12],
            "printer": printer.name,
            "printer_entity": printer.status_entity,
            "serial": printer.serial,
            "name": task or gcode or "Druck",
            "file": gcode,
            "started_at": started.isoformat(),
            "planned_grams": _float(printer.sibling_state(hass, UID_WEIGHT)) if current else None,
            "energy_start": self._energy(printer),
            "spools_start": self._spool_snapshot(printer),
            "tags_seen": sorted(printer.tray_tags(hass)),
            "used_tags": [],
            "used_trays": [],
            "partial": partial,
        }
        self._note_tray(printer, job)
        self.active[printer.status_entity] = job
        _LOGGER.info("%s: print started - %s", printer.name, job["name"])
        await self._save()
        async_dispatcher_send(hass, SIGNAL_UPDATED)

    def _interrupt(self, printer: Printer, job: dict[str, Any]) -> None:
        job["offline_since"] = dt_util.utcnow().isoformat()
        job["offline_energy"] = self._energy(printer)
        _LOGGER.info("%s: print interrupted (printer offline) - %s", printer.name, job.get("name"))
        self.hass.async_create_task(self._save())
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def _same_task(self, printer: Printer, job: dict[str, Any]) -> bool:
        task = printer.sibling_state(self.hass, UID_TASK)
        return not task or task in (job.get("name"), job.get("file"))

    async def _replace_interrupted(self, printer: Printer, job: dict[str, Any]) -> None:
        eid = printer.status_entity
        await self._end(printer, "cancelled", ended_at=job.get("offline_since"),
                        energy=job.get("offline_energy"))
        # Book it right away so the slot is free for the new print.
        cancel = self._timers.pop(eid, None)
        if cancel:
            cancel()
        await self._settle(eid)
        await self._begin(printer)

    def _resume(self, printer: Printer, job: dict[str, Any]) -> None:
        since = job.pop("offline_since", None)
        job.pop("offline_energy", None)
        if since:
            job.setdefault("interruptions", []).append(
                {"from": since, "to": dt_util.utcnow().isoformat()})
            _LOGGER.info("%s: print resumed after interruption - %s", printer.name, job.get("name"))
        self.hass.async_create_task(self._save())
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def _end(self, printer: Printer, state: str, ended_at: str | None = None,
                   energy: float | None = None) -> None:
        job = self.active.get(printer.status_entity)
        if not job or job.get("ended_at"):
            return
        since = job.pop("offline_since", None)
        job.pop("offline_energy", None)
        if since and ended_at is None:
            # Finished/failed while it was unreachable: note the gap.
            job.setdefault("interruptions", []).append(
                {"from": since, "to": dt_util.utcnow().isoformat()})
        self._refresh_meta(printer, job, at_end=True)
        job["ended_at"] = ended_at or dt_util.utcnow().isoformat()
        job["result"] = ("finished" if state == RESULT_FINISHED
                         else "failed" if state == RESULT_FAILED else "cancelled")
        job["energy_end"] = energy if energy is not None else self._energy(printer)
        # Titelbild nur, wenn die Modelldaten der Integration zu diesem Druck gehören
        if _meta_current(printer.sibling_state(self.hass, UID_TASK) or job.get("name"),
                         printer.sibling_state(self.hass, UID_GCODE)):
            job["image"] = await self._save_cover(printer, job["id"])
        else:
            job["image"] = None
        if state not in OFF_STATES:
            # The printer stays on after the print: from here it is idle.
            if ended_at is None:
                await self._open_idle(printer, started=job["ended_at"], energy=job["energy_end"])
            # Back-dated end (interrupted print replaced by a new one): no idle phase.
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
        filaments, source = _book_filaments(job, after)
        e0, e1 = job.get("energy_start"), job.get("energy_end")
        energy = round(e1 - e0, 4) if e0 is not None and e1 is not None and e1 >= e0 else None
        price = _float(_state(self.hass, self.price_entity))
        started = dt_util.parse_datetime(job["started_at"])
        ended = dt_util.parse_datetime(job["ended_at"])
        record = {
            k: job.get(k) for k in ("id", "printer", "printer_entity", "serial", "name",
                                    "file", "started_at", "ended_at",
                                    "result", "planned_grams", "image", "partial",
                                    "interruptions")
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

    # -- idle phases -------------------------------------------------------
    async def _open_idle(self, printer: Printer, partial: bool = False,
                         started: str | None = None, energy: float | None = None,
                         resume: bool = False) -> None:
        """The printer is on and not printing: start (or continue) an idle phase."""
        eid = printer.status_entity
        if eid in self.idle_active:
            return
        session = self._resumable_idle(eid) if resume else None
        if session is None:
            session = {
                "id": uuid.uuid4().hex[:12],
                "printer": printer.name,
                "printer_entity": eid,
                "started_at": started or dt_util.utcnow().isoformat(),
                "energy_start": energy if energy is not None else self._energy(printer),
                "partial": partial,
            }
        self.idle_active[eid] = session
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def _resumable_idle(self, eid: str) -> dict[str, Any] | None:
        """The idle phase this printer dropped off from a moment ago, taken back."""
        for i in range(len(self.idle) - 1, -1, -1):
            rec = self.idle[i]
            if rec.get("printer_entity") != eid:
                continue
            ended = dt_util.parse_datetime(rec.get("ended_at") or "")
            if rec.get("end_reason") != "off" or rec.get("energy_start") is None or ended is None \
                    or dt_util.utcnow() - ended > timedelta(minutes=IDLE_RESUME_MINUTES):
                return None
            self.idle.pop(i)
            return {k: rec.get(k) for k in ("id", "printer", "printer_entity", "started_at",
                                            "energy_start", "partial")}
        return None

    async def _close_idle(self, printer: Printer, reason: str, partial: bool = False) -> None:
        """End the printer's idle phase and book its energy ('print' or 'off')."""
        session = self.idle_active.pop(printer.status_entity, None)
        if session is None:
            return
        ended = dt_util.utcnow()
        started = dt_util.parse_datetime(session["started_at"])
        duration = int((ended - started).total_seconds()) if started else None
        e0, e1 = session.get("energy_start"), self._energy(printer)
        energy = round(e1 - e0, 4) if e0 is not None and e1 is not None and e1 >= e0 else None
        if (duration or 0) < IDLE_MIN_SECONDS and not (energy and energy >= 0.001):
            await self._save()
            return
        price = _float(_state(self.hass, self.price_entity))
        cost = round(energy * price, 4) if energy is not None and price is not None else None
        self.idle.append({
            "id": session["id"],
            "type": "idle",
            "name": "Leerlauf",
            "result": "idle",
            "printer": printer.name,
            "printer_entity": printer.status_entity,
            "started_at": session["started_at"],
            "ended_at": ended.isoformat(),
            "duration_s": duration,
            "end_reason": reason,
            "energy_start": e0,
            "energy_end": e1,
            "energy_kwh": energy,
            "energy_price": price,
            "energy_cost": cost,
            "total_cost": cost,
            "partial": bool(session.get("partial") or partial),
        })
        await self._save()
        _LOGGER.debug("%s: idle phase booked - %s s, %s kWh", printer.name, duration, energy)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    def active_running(self) -> list[dict[str, Any]]:
        """Running prints with the energy they have drawn so far."""
        price = _float(_state(self.hass, self.price_entity))
        out = []
        for eid, job in self.active.items():
            printer = self.printers.get(eid)
            e0 = job.get("energy_start")
            e1 = job.get("energy_end") or (self._energy(printer) if printer else None)
            energy = round(e1 - e0, 4) if e0 is not None and e1 is not None and e1 >= e0 else None
            out.append({
                **{k: v for k, v in job.items() if k not in ("spools_start", "tags_seen")},
                "printer": printer.name if printer else job.get("printer"),
                "status": ("interrupted" if job.get("offline_since")
                           else "paused" if printer and _state(self.hass, eid) == "pause"
                           else "printing"),
                "energy_kwh": energy,
                "energy_cost": round(energy * price, 4)
                if energy is not None and price is not None else None,
            })
        return out

    def idle_running(self) -> list[dict[str, Any]]:
        """Open idle phases with what they have drawn so far."""
        price = _float(_state(self.hass, self.price_entity))
        out = []
        for eid, session in self.idle_active.items():
            printer = self.printers.get(eid)
            e0 = session.get("energy_start")
            e1 = self._energy(printer) if printer else None
            energy = round(e1 - e0, 4) if e0 is not None and e1 is not None and e1 >= e0 else None
            out.append({
                **session,
                "printer": printer.name if printer else session.get("printer"),
                "energy_kwh": energy,
                "energy_cost": round(energy * price, 4)
                if energy is not None and price is not None else None,
            })
        return out

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
            meta = _spool_meta(m.group(1), st)
            if meta is None:
                continue
            tray, tag = meta["tray"], meta["tag"]
            mine = (printer.serial and tray.startswith(printer.serial + "_")) or (tag and tag in tags)
            if mine or meta["id"] in keep:
                out[meta["id"]] = meta
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
    async def async_rebook(self, job_id: str, spool_id: int,
                           grams: float | None = None) -> dict[str, Any]:
        """Book a finished print's filament to one spool by hand."""
        job = next((j for j in self.jobs if j.get("id") == job_id), None)
        if job is None:
            raise ValueError(f"Kein Druck mit ID {job_id}")
        grams = grams if grams is not None else job.get("planned_grams")
        if not grams or grams <= 0:
            raise ValueError("Keine Grammzahl angegeben und keine Slicer-Schätzung vorhanden")
        st = self.hass.states.get(f"sensor.spoolman_spool_{spool_id}")
        meta = _spool_meta(str(spool_id), st) if st else None
        if meta is None:
            raise ValueError(f"Spule {spool_id} nicht in Spoolman gefunden")
        job["filaments"] = [_filament(str(spool_id), round(float(grams), 2), meta)]
        job["filament_source"] = "manual"
        job.update(summarize(job.get("energy_kwh"), job.get("energy_price"), job["filaments"]))
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return job

    async def async_update_job(self, job_id: str, ended_at: datetime | None = None,
                               result: str | None = None,
                               energy_kwh: float | None = None) -> dict[str, Any]:
        """Correct a booked print by hand: end time, result, energy."""
        job = next((j for j in self.jobs if j.get("id") == job_id), None)
        if job is None:
            raise ValueError(f"Kein Druck mit ID {job_id}")
        if ended_at is not None:
            end = dt_util.as_utc(ended_at)
            job["ended_at"] = end.isoformat()
            started = dt_util.parse_datetime(job["started_at"])
            job["duration_s"] = int((end - started).total_seconds()) if started else None
        if result is not None:
            job["result"] = result
        if energy_kwh is not None:
            job["energy_kwh"] = round(float(energy_kwh), 4)
        job.update(summarize(job.get("energy_kwh"), job.get("energy_price"),
                             job.get("filaments") or []))
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return job

    async def async_delete(self, job_id: str) -> bool:
        """Remove a print or an idle phase by its id."""
        before = len(self.jobs) + len(self.idle)
        self.jobs = [j for j in self.jobs if j.get("id") != job_id]
        self.idle = [j for j in self.idle if j.get("id") != job_id]
        if len(self.jobs) + len(self.idle) == before:
            return False
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return True


def _book_filaments(job: dict[str, Any], after: dict[str, dict[str, Any]]
                    ) -> tuple[list[dict[str, Any]], str | None]:
    """Grams and cost per spool of a settled job, and where the grams came from.

    Only spools whose tray fed the nozzle during the print count, so an AMS that
    re-reads its tags (and corrects the remaining weight of every spool) at the
    start of a print no longer books the other colours. Spoolman's figures are
    taken when they fit the slicer's estimate; otherwise the slicer's weight is
    spread over the spools used.
    """
    start = job["spools_start"]
    known = {**start, **after}
    used = spool_usage({k: v["used"] for k, v in start.items()},
                       {k: v["used"] for k, v in after.items()})
    tags, trays = set(job.get("used_tags") or []), set(job.get("used_trays") or [])
    active = sorted(
        sid for sid, m in known.items()
        if (m.get("tag") and m["tag"] in tags) or (m.get("tray") and m["tray"] in trays)
    )
    if active:
        used = {sid: g for sid, g in used.items() if sid in active}
    planned = job.get("planned_grams") if job.get("result") == "finished" else None
    if not planned or spoolman_plausible(used, planned):
        return [_filament(sid, g, known[sid]) for sid, g in used.items()], \
            "spoolman" if used else None
    targets = active or sorted(used)
    if not targets:
        # Nothing known about the trays: only a single loaded spool is a safe guess.
        loaded = [sid for sid, m in start.items() if m.get("tag") in job.get("tags_seen", [])]
        targets = loaded if len(loaded) == 1 else []
    grams = split_grams(planned, targets, used)
    if grams:
        return [_filament(sid, g, known[sid]) for sid, g in grams.items()], "slicer"
    return [{"spool_id": None, "name": "laut Slicer", "color": None, "material": None,
             "grams": planned, "price_per_g": None, "cost": None}], "slicer"


def _filament(sid: str, grams: float, meta: dict[str, Any]) -> dict[str, Any]:
    ppg = meta.get("ppg")
    return {
        "spool_id": int(sid), "name": meta.get("name"), "color": meta.get("color"),
        "material": meta.get("material"), "grams": grams,
        "price_per_g": round(ppg, 5) if ppg else None,
        "cost": round(grams * ppg, 4) if ppg else None,
    }


def _spool_meta(sid: str, st: State) -> dict[str, Any] | None:
    """What the cost of a spool needs, from its Spoolman sensor."""
    a = st.attributes
    used = _float(a.get("used_weight"))
    if used is None:
        return None
    return {
        "id": sid, "used": used,
        "tag": str(a.get("extra_tag") or "").strip('"').upper(),
        "tray": str(a.get("extra_active_tray") or "").strip('"'),
        "name": " ".join(x for x in (a.get("filament_vendor_name"),
                                      a.get("filament_material"),
                                      a.get("filament_name")) if x) or a.get("friendly_name"),
        "material": a.get("filament_material"),
        "color": a.get("filament_color_hex")
        or (a.get("filament_multi_color_hexes") or "").split(",")[0] or None,
        "ppg": price_per_gram(dict(a)),
    }


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
