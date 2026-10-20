# Changelog

## [2.2.2] - 2026-10-20

### Added
- Running prints show the energy drawn so far and its cost (refreshed with the card, every minute).

## [2.2.1] - 2026-10-20

### Fixed
- Removed the "Modell auf MakerWorld" link: the number in front of the downloaded G-code name (e.g. `21863866-Name.gcode`) is the file size ha-bambulab prepends, not a MakerWorld model ID.
- Stale model data: when a print starts from the SD root ("Send" in Bambu Studio, or a start via MQTT from Home Assistant), ha-bambulab does not download the new model, so the downloaded G-code name, the slicer weight and the cover image still belong to the previous print. A job now only takes over file name, planned grams and cover image when the downloaded G-code matches the task name.

## [2.2.0] - 2026-10-05

### Added
- Idle phases: the time a printer is switched on without printing and the
  electricity it draws meanwhile. A phase starts when a print ends or when a
  printer comes on without printing, and ends with the next print or when the
  printer goes offline (e.g. switched off by its smart plug). A printer that
  drops off for less than 5 minutes (lost connection) continues its phase.
- The card has a view switch *Drucke / Leerlauf*: the idle view lists every
  phase with printer, time, duration, kWh and cost, shows printers idling right
  now, and filters by printer and month like the prints. The print view gets a
  *Leerlauf* figure that opens it. New card option `view: idle`.
- Sensors `sensor.leerlaufkosten_gesamt` and `sensor.leerlaufkosten_diesen_monat`
  (attributes: phases, kWh, hours, cost per printer, printers idling now).
- `export_csv` includes the idle phases (name `Leerlauf`, result `idle`);
  `delete_job` also removes an idle phase by its id.

## [2.1.0] - 2026-09-28

### Fixed
- Only spools whose AMS tray actually fed the nozzle during the print are
  costed. An AMS reading its tags at the start of a print corrects the
  remaining weight of every loaded spool in Spoolman; those corrections were
  booked as usage (a single-colour print showed up with three colours).
- Spoolman figures that only move in 10 g steps (AMS remaining percentage of a
  Bambu RFID spool) or that are far off the slicer's estimate are no longer
  taken as usage of a finished print; the slicer's weight is spread over the
  spools used instead.

### Added
- Service `print_cost_analyzer.rebook_job` to book a print's filament to one
  spool by hand (defaults to the slicer's estimate).

## [2.0.3] - 2026-09-25

### Fixed
- A printer that finished while unreachable and comes back as `finish` now ends
  the job (before, it stayed running forever).
- At the end of a print its start is taken from the printer when the job was
  noted much later (missed start), and the print is marked as partial.
- If the energy meter was unavailable when a job began, the reading is taken as
  soon as it is available again instead of costing no electricity at all.

## [2.0.2] - 2026-09-25

### Fixed
- A printer coming back from unavailable while printing (HA restart, lost
  connection) is no longer taken for a fresh start: the printer's own start time
  is used and the print is marked as partially observed.
- Prints recorded that way by 2.0.0/2.0.1 are corrected on start-up.
- Task name, file, planned weight and start time that arrive after the print
  status (typical after a reconnect) are filled in, instead of "Druck".
- Running prints show the short printer name.

## [2.0.1] - 2026-09-25

### Changed
- Printer names without the serial ha-bambulab appends ("H2D_0948…" -> "H2D"),
  also for a print that was already running when updating.

## [2.0.0] - 2026-09-25

Complete rewrite. Prints are now recorded automatically instead of by hand.

### Added
- Automatic print tracking for ha-bambulab printers: start and end from the
  print status, name, file, MakerWorld id and cover image of every print.
- Filament per spool from Spoolman's `used_weight` (as booked by OpenSpoolMan),
  correct for multi-colour and cancelled prints; slicer estimate as fallback.
- Energy per print from the plug's energy meter, priced with any EUR/kWh entity.
- Print history in Home Assistant's own storage (in every backup), CSV export.
- Dashboard card `custom:print-cost-card`, served by the integration.
- Sensors: total cost, cost this month, number of prints, last print.

### Removed
- InfluxDB dependency, manual `add_print_job` service, polling coordinator.
