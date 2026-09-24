# Changelog

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
