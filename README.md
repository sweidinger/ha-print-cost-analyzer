# 3D Print Cost Analyzer

Records every 3D print automatically and works out what it cost – electricity
and filament, per print, in Home Assistant. No external database.

## How it works

For each printer of the [ha-bambulab](https://github.com/greghesp/ha-bambulab)
integration it follows the print status:

- **Print starts:** it notes the plug's energy meter and the `used_weight` of every
  Spoolman spool loaded in that printer (matched by `extra.active_tray` or the Bambu
  spool id in `extra.tag`).
- **Print ends:** it saves the cover image, waits a few minutes (setting *wait after
  print end*) so OpenSpoolMan can book the last layers to Spoolman, then books the print:
  - **Electricity:** kWh difference × your price entity (e.g. `input_number.strompreis`)
  - **Filament:** grams per spool from Spoolman × price per gram (spool price, else
    filament price, divided by its weight). Multi-colour and cancelled prints come
    out right because OpenSpoolMan books what was actually printed.
  - If nothing was booked to Spoolman, the slicer's planned weight is used and the
    print is marked as estimated.

Prints running while Home Assistant restarts are resumed; a print that finished
while HA was down is booked on start-up.

## Installation

HACS → Integrations → ⋮ → Custom repositories → this repository (type Integration),
install, restart Home Assistant, then *Settings → Devices & services → Add
integration → 3D Print Cost Analyzer*.

Setup asks for the printers, the price entity and the wait time, then for each
printer's energy meter (pre-filled when the meter's name contains the printer's).

## Dashboard

The card is served by the integration, no resource needed:

```yaml
type: custom:print-cost-card
title: 3D-Druckkosten
```

It lists every print with picture, printer, time, duration and total; tap a print
for electricity, filament per spool and the total. Filter by printer and month.

## Entities, services, events

- `sensor.druckkosten_gesamt`, `sensor.druckkosten_diesen_monat` – with energy and
  filament split as attributes
- `sensor.anzahl_drucke`, `sensor.letzter_druck`
- `print_cost_analyzer.export_csv` – writes `/config/print_cost_analyzer.csv`
- `print_cost_analyzer.delete_job` – removes a print by id
- Event `print_cost_analyzer_job_finished` – fired with the full record of each print

## Requirements

- ha-bambulab (print status, task name, cover image, print weight)
- Spoolman integration; OpenSpoolMan (or anything else) booking usage to Spoolman
- Prices in Spoolman (spool or filament)
- An energy meter per printer, e.g. a Shelly Plug (optional)

## Development

```bash
pip install -r requirements_test.txt
pytest
```
