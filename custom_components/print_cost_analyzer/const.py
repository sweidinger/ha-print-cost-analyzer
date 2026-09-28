"""Constants for the 3D Print Cost Analyzer."""
from __future__ import annotations

DOMAIN = "print_cost_analyzer"

CONF_PRINTERS = "printers"            # list of print-status entity ids (bambu_lab)
CONF_ENERGY = "energy"                # {status_entity_id: energy_entity_id}
CONF_PRICE_ENTITY = "price_entity"    # electricity price entity (EUR/kWh)
CONF_SETTLE_MINUTES = "settle_minutes"

DEFAULT_PRICE_ENTITY = "input_number.strompreis"
DEFAULT_SETTLE_MINUTES = 5

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.jobs"

EVENT_JOB_FINISHED = f"{DOMAIN}_job_finished"
SIGNAL_UPDATED = f"{DOMAIN}_updated"

# print_status values reported by ha-bambulab
ACTIVE_STATES = {"prepare", "running", "pause", "slicing", "init"}
# Before the print proper the AMS may run through every slot to read the tags;
# a tray seen active then was not necessarily printed with.
PREP_STATES = {"prepare", "slicing", "init"}
RESULT_FINISHED = "finish"
RESULT_FAILED = "failed"

# unique_id suffixes of the sibling entities on a ha-bambulab printer device
UID_STATUS = "_print_status"
UID_TASK = "_subtask_name"
UID_GCODE = "_gcode_file_downloaded"
UID_WEIGHT = "_print_weight"
UID_START = "_start_time"
UID_COVER = "_cover_image"
UID_ACTIVE_TRAY = "_active_tray"

IMAGE_DIR = "www/print_cost_analyzer"
IMAGE_URL = "/local/print_cost_analyzer"
CARD_URL = "/print_cost_analyzer/print-cost-card.js"
