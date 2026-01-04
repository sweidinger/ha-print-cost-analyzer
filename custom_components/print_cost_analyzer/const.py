"""Constants for the Print Cost Analyzer integration."""
from homeassistant.const import CONF_URL, CONF_USERNAME, CONF_PASSWORD, CONF_TOKEN

DOMAIN = "print_cost_analyzer"

# Spoolman configuration
CONF_SPOOLMAN_URL = "spoolman_url"
CONF_SPOOLMAN_TOKEN = "spoolman_token"

# Shelly Plug configuration
CONF_SHELLY_POWER_ENTITIES = "shelly_power_entities"
CONF_SHELLY_ENERGY_ENTITIES = "shelly_energy_entities"

# AMS configuration
CONF_AMS_ENTITIES = "ams_entities"

# InfluxDB configuration
CONF_INFLUXDB_URL = "influxdb_url"
CONF_INFLUXDB_TOKEN = "influxdb_token"
CONF_INFLUXDB_ORG = "influxdb_org"
CONF_INFLUXDB_BUCKET = "influxdb_bucket"

# Energy cost configuration
CONF_ENERGY_COST_PER_KWH = "energy_cost_per_kwh"
CONF_ENERGY_COST_ENTITY = "energy_cost_entity"
CONF_ENERGY_COST_SOURCE = "energy_cost_source"  # "fixed" or "entity"
DEFAULT_ENERGY_COST_PER_KWH = 0.30  # €0.30 per kWh

# Update interval in seconds
SCAN_INTERVAL = 60