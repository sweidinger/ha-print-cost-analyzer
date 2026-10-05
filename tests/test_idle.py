"""Idle phases: a printer switched on without printing, and what it drew."""
from datetime import timedelta

from tests.test_tracker import STATUS, _setup_printer, _tracker

METER = "sensor.shelly_h2d"


def _meter(hass, kwh):
    hass.states.async_set(METER, str(kwh), {"unit_of_measurement": "kWh"})


async def _status(hass, state):
    hass.states.async_set(STATUS, state)
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def test_idle_after_a_print_until_switched_off(hass, freezer):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    tracker.idle_active.clear()                  # started idle at setup; not this test's subject
    await _status(hass, "running")
    _meter(hass, 100.5)
    await _status(hass, "finish")
    assert len(tracker.jobs) == 1
    session = tracker.idle_active[STATUS]
    assert session["energy_start"] == 100.5
    assert session["started_at"] == tracker.jobs[-1]["ended_at"]

    freezer.tick(timedelta(hours=1))
    _meter(hass, 100.55)
    running = tracker.idle_running()[0]
    assert running["energy_kwh"] == 0.05
    await _status(hass, "offline")                # the plug cut the power

    assert tracker.idle_active == {}
    rec = tracker.idle[-1]
    assert rec["end_reason"] == "off"
    assert rec["duration_s"] == 3600
    assert rec["energy_kwh"] == 0.05
    assert rec["energy_cost"] == 0.015 and rec["total_cost"] == 0.015
    assert rec["partial"] is False


async def test_next_print_ends_the_idle_phase(hass, freezer):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    assert STATUS in tracker.idle_active          # idle printer at start-up
    freezer.tick(timedelta(minutes=20))
    _meter(hass, 100.02)
    await _status(hass, "prepare")
    rec = tracker.idle[-1]
    assert rec["end_reason"] == "print"
    assert rec["energy_kwh"] == 0.02
    assert rec["partial"] is True                 # its start was not seen
    job = next(iter(tracker.active.values()))
    assert job["energy_start"] == rec["energy_end"]  # no gap, no double counting


async def test_switching_on_without_printing_starts_an_idle_phase(hass, freezer):
    _setup_printer(hass)
    hass.states.async_set(STATUS, "unavailable")
    tracker, _ = await _tracker(hass)
    assert tracker.idle_active == {}
    await _status(hass, "idle")
    assert tracker.idle_active[STATUS]["partial"] is False
    freezer.tick(timedelta(minutes=30))
    _meter(hass, 100.01)
    await _status(hass, "unavailable")
    assert tracker.idle[-1]["duration_s"] == 1800


async def test_a_short_drop_out_continues_the_same_phase(hass, freezer):
    _setup_printer(hass)
    hass.states.async_set(STATUS, "unavailable")
    tracker, _ = await _tracker(hass)
    await _status(hass, "idle")
    first = tracker.idle_active[STATUS]["id"]
    freezer.tick(timedelta(minutes=10))
    await _status(hass, "unavailable")            # lost connection
    freezer.tick(timedelta(minutes=2))
    await _status(hass, "idle")                   # back
    assert tracker.idle == []
    assert tracker.idle_active[STATUS]["id"] == first
    freezer.tick(timedelta(minutes=10))
    _meter(hass, 100.03)
    await _status(hass, "offline")
    assert len(tracker.idle) == 1
    assert tracker.idle[0]["duration_s"] == 22 * 60
    assert tracker.idle[0]["energy_kwh"] == 0.03


async def test_switched_on_again_later_is_a_new_phase(hass, freezer):
    _setup_printer(hass)
    hass.states.async_set(STATUS, "unavailable")
    tracker, _ = await _tracker(hass)
    await _status(hass, "idle")
    freezer.tick(timedelta(minutes=10))
    await _status(hass, "offline")
    freezer.tick(timedelta(hours=3))
    await _status(hass, "idle")
    assert len(tracker.idle) == 1
    assert tracker.idle_active[STATUS]["id"] != tracker.idle[0]["id"]


async def test_status_flicker_is_not_kept(hass):
    _setup_printer(hass)
    hass.states.async_set(STATUS, "unavailable")
    tracker, _ = await _tracker(hass)
    await _status(hass, "idle")
    await _status(hass, "unavailable")
    assert tracker.idle == [] and tracker.idle_active == {}


async def test_open_phase_survives_a_restart_and_is_closed_if_off(hass, freezer):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    session = dict(tracker.idle_active[STATUS])
    await tracker.async_stop()
    freezer.tick(timedelta(hours=2))
    _meter(hass, 100.04)
    hass.states.async_set(STATUS, "unavailable")  # switched off while HA was down
    tracker2, _ = await _tracker(hass)
    assert tracker2.idle_active == {}
    rec = tracker2.idle[-1]
    assert rec["id"] == session["id"]
    assert rec["energy_kwh"] == 0.04
    assert rec["partial"] is True


async def test_idle_phase_can_be_deleted(hass, freezer):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    freezer.tick(timedelta(minutes=5))
    await _status(hass, "offline")
    rid = tracker.idle[-1]["id"]
    assert await tracker.async_delete(rid) is True
    assert tracker.idle == []
