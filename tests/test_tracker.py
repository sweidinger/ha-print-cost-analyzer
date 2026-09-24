"""A print from start to booking, on a real (test) Home Assistant."""
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.print_cost_analyzer.const import EVENT_JOB_FINISHED
from custom_components.print_cost_analyzer.tracker import Printer, PrintTracker

SERIAL = "0948BB520500417"
STATUS = "sensor.h2d_druckstatus"


def _setup_printer(hass):
    bambu = MockConfigEntry(domain="bambu_lab")
    bambu.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=bambu.entry_id, identifiers={("bambu_lab", SERIAL)}, name="H2D")
    ent = er.async_get(hass)
    for suffix, eid in (("_print_status", "h2d_druckstatus"), ("_subtask_name", "h2d_task"),
                        ("_gcode_file_downloaded", "h2d_gcode"), ("_print_weight", "h2d_weight"),
                        ("_start_time", "h2d_start"), ("_active_tray", "h2d_active")):
        ent.async_get_or_create("sensor", "bambu_lab", SERIAL + suffix,
                                suggested_object_id=eid, device_id=dev.id,
                                config_entry=bambu)
    hass.states.async_set(STATUS, "idle")
    hass.states.async_set("sensor.h2d_task", "Key Holder_plate_1")
    hass.states.async_set("sensor.h2d_gcode", "31879733-Key Holder_plate_1.gcode")
    hass.states.async_set("sensor.h2d_weight", "20.0")
    hass.states.async_set("sensor.h2d_start", "2026-09-24T17:32:00+00:00")
    hass.states.async_set("sensor.h2d_active", "PLA", {"tray_uuid": "TAGA"})
    hass.states.async_set("sensor.shelly_h2d", "100.0", {"unit_of_measurement": "kWh", "device_class": "energy"})
    hass.states.async_set("input_number.strompreis", "0.3")


def _spool(hass, sid, used, tray="", tag="", price=None):
    attrs = {"used_weight": used, "extra_active_tray": tray, "extra_tag": tag,
             "initial_weight": 1000, "filament_vendor_name": "Bambu Lab",
             "filament_material": "PLA", "filament_name": f"Farbe {sid}", "filament_color_hex": "112233"}
    if price is not None:
        attrs["price"] = price
    hass.states.async_set(f"sensor.spoolman_spool_{sid}", str(1000 - used), attrs)


async def _tracker(hass, settle=0):
    printer = Printer(hass, STATUS, "sensor.shelly_h2d")
    tracker = PrintTracker(hass, [printer], "input_number.strompreis", settle)
    await tracker.async_start()
    return tracker, printer


async def test_resolves_siblings_by_serial(hass):
    _setup_printer(hass)
    printer = Printer(hass, STATUS, None)
    assert printer.serial == SERIAL
    assert printer.name == "H2D"
    assert printer.siblings["_subtask_name"] == "sensor.h2d_task"
    assert printer.tray_tags(hass) == {"TAGA"}


async def test_multicolour_print_is_costed_per_spool(hass):
    _setup_printer(hass)
    _spool(hass, 4, 100.0, tray=f"{SERIAL}_1_0", price=20.0)     # by tray
    _spool(hass, 6, 50.0, tag="taga", price=25.0)                 # by tag only
    _spool(hass, 9, 10.0, tray="OTHERPRINTER_0_1", price=30.0)    # other printer
    events = []
    hass.bus.async_listen(EVENT_JOB_FINISHED, lambda e: events.append(e.data))
    tracker, _ = await _tracker(hass)

    hass.states.async_set(STATUS, "prepare")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    assert len(tracker.active) == 1

    # OpenSpoolMan books 12 g and 3 g, the plug counts 0.5 kWh; spool 9 is someone else's
    _spool(hass, 4, 112.0, tray=f"{SERIAL}_1_0", price=20.0)
    _spool(hass, 6, 53.0, tag="taga", price=25.0)
    _spool(hass, 9, 40.0, tray="OTHERPRINTER_0_1", price=30.0)
    hass.states.async_set("sensor.shelly_h2d", "100.5", {"unit_of_measurement": "kWh"})
    hass.states.async_set(STATUS, "finish")
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    assert tracker.active == {}
    job = tracker.jobs[-1]
    assert job["result"] == "finished"
    assert job["name"] == "Key Holder_plate_1"
    assert job["makerworld_id"] == "31879733"
    assert job["energy_kwh"] == 0.5
    assert job["energy_cost"] == 0.15
    grams = {f["spool_id"]: f["grams"] for f in job["filaments"]}
    assert grams == {4: 12.0, 6: 3.0}
    assert job["filament_cost"] == round(12 * 0.02 + 3 * 0.025, 4)
    assert job["total_cost"] == round(0.15 + 0.24 + 0.075, 4)
    assert job["filament_source"] == "spoolman"
    assert events and events[0]["id"] == job["id"]


async def test_falls_back_to_slicer_weight_when_nothing_was_booked(hass):
    _setup_printer(hass)
    _spool(hass, 6, 50.0, tag="TAGA", price=25.0)
    tracker, _ = await _tracker(hass)
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "finish")
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    job = tracker.jobs[-1]
    assert job["filament_source"] == "slicer"
    assert job["filaments"][0]["grams"] == 20.0
    assert job["filaments"][0]["cost"] == 0.5


async def test_cancelled_print_is_marked(hass):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "idle")
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert tracker.jobs[-1]["result"] == "cancelled"
    assert tracker.jobs[-1]["filaments"] == []


async def test_unavailable_does_not_end_a_print(hass):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass)
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    assert len(tracker.active) == 1 and tracker.jobs == []


async def test_running_job_survives_a_restart(hass):
    _setup_printer(hass)
    tracker, _ = await _tracker(hass, settle=5)
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    await tracker.async_stop()
    # HA restarts; meanwhile the print finished
    hass.states.async_set(STATUS, "finish")
    tracker2, _ = await _tracker(hass, settle=0)
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert tracker2.jobs and tracker2.jobs[-1]["result"] == "finished"


async def test_print_already_running_at_startup_is_picked_up(hass):
    _setup_printer(hass)
    hass.states.async_set(STATUS, "running")
    tracker, _ = await _tracker(hass)
    job = next(iter(tracker.active.values()))
    assert job["partial"] is True
    assert job["started_at"].startswith("2026-09-24T17:32")


async def test_booking_waits_for_the_settle_time(hass):
    """OpenSpoolMan books a little after the printer reports finish."""
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    _setup_printer(hass)
    _spool(hass, 4, 100.0, tray=f"{SERIAL}_1_0", price=20.0)
    tracker, _ = await _tracker(hass, settle=5)
    hass.states.async_set(STATUS, "running")
    await hass.async_block_till_done()
    hass.states.async_set(STATUS, "finish")
    await hass.async_block_till_done()
    assert tracker.jobs == []                      # not booked yet
    _spool(hass, 4, 108.0, tray=f"{SERIAL}_1_0", price=20.0)   # late booking
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert tracker.jobs[-1]["filaments"][0]["grams"] == 8.0
