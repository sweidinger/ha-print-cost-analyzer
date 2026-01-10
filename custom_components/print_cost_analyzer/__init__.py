"""3D Print Cost Analyzer integration for Home Assistant."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import aiohttp
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    GLOBAL_CONFIG_STORAGE_KEY,
    GLOBAL_CONFIG_STORAGE_VERSION,
    CONF_SPOOLMAN_URL,
    CONF_SPOOLMAN_TOKEN,
    CONF_SPOOLMAN_SPOOL_IDS,
    CONF_SHELLY_POWER_ENTITIES,
    CONF_SHELLY_ENERGY_ENTITIES,
    CONF_AMS_ENTITIES,
    CONF_INFLUXDB_URL,
    CONF_INFLUXDB_TOKEN,
    CONF_INFLUXDB_ORG,
    CONF_INFLUXDB_BUCKET,
    CONF_ENERGY_COST_PER_KWH,
    CONF_ENERGY_COST_ENTITY,
    CONF_ENERGY_COST_SOURCE,
    DEFAULT_ENERGY_COST_PER_KWH,
    SCAN_INTERVAL,
)
from .service import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]

__version__ = "2024.8.8"


class PrintCostCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the APIs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, global_config: Dict[str, Any]) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.printer_name = entry.data.get(CONF_NAME) or entry.title
        self.spoolman_spool_ids = entry.data.get(CONF_SPOOLMAN_SPOOL_IDS, [])
        self.shelly_power_entities = entry.data.get(CONF_SHELLY_POWER_ENTITIES, [])
        self.shelly_energy_entities = entry.data.get(CONF_SHELLY_ENERGY_ENTITIES, [])
        self.ams_entities = entry.data.get(CONF_AMS_ENTITIES, [])
        self.spoolman_url = global_config.get(CONF_SPOOLMAN_URL, entry.data.get(CONF_SPOOLMAN_URL))
        self.spoolman_token = global_config.get(CONF_SPOOLMAN_TOKEN, entry.data.get(CONF_SPOOLMAN_TOKEN))
        self.influxdb_url = global_config.get(CONF_INFLUXDB_URL, entry.data.get(CONF_INFLUXDB_URL))
        self.influxdb_token = global_config.get(CONF_INFLUXDB_TOKEN, entry.data.get(CONF_INFLUXDB_TOKEN))
        self.influxdb_org = global_config.get(CONF_INFLUXDB_ORG, entry.data.get(CONF_INFLUXDB_ORG))
        self.influxdb_bucket = global_config.get(CONF_INFLUXDB_BUCKET, entry.data.get(CONF_INFLUXDB_BUCKET))
        self.energy_cost_source = global_config.get(
            CONF_ENERGY_COST_SOURCE, entry.data.get(CONF_ENERGY_COST_SOURCE, "fixed")
        )
        self.energy_cost_per_kwh = global_config.get(
            CONF_ENERGY_COST_PER_KWH,
            entry.data.get(CONF_ENERGY_COST_PER_KWH, DEFAULT_ENERGY_COST_PER_KWH),
        )
        self.energy_cost_entity = global_config.get(CONF_ENERGY_COST_ENTITY, entry.data.get(CONF_ENERGY_COST_ENTITY))

        self.influxdb_client: Optional[InfluxDBClient] = None
        self.spool_data: Dict[str, Any] = {}
        self.energy_data: Dict[str, Any] = {}
        self.ams_data: Dict[str, Any] = {}
        self.print_history: List[Dict[str, Any]] = []
        self.spoolman_connected: bool = False
        self.influxdb_connected: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        try:
            # Initialize InfluxDB client
            self.influxdb_client = InfluxDBClient(
                url=self.influxdb_url,
                token=self.influxdb_token,
                org=self.influxdb_org,
            )
            self.influxdb_connected = True
            _LOGGER.info("InfluxDB client initialized successfully")
        except Exception as e:
            self.influxdb_connected = False
            _LOGGER.error("Failed to initialize InfluxDB client: %s", e)
            raise

    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data via library."""
        try:
            await asyncio.gather(
                self._fetch_spoolman_data(),
                self._fetch_shelly_energy_data(),
                self._fetch_ams_data(),
                self._fetch_influxdb_print_data(),
            )
            await self._calculate_costs()

            return {
                "spools": self.spool_data,
                "energy": self.energy_data,
                "ams": self.ams_data,
                "print_history": self.print_history,
                "total_cost": self._calculate_total_cost(),
                "energy_cost_per_kwh": await self._get_energy_cost_per_kwh(),
                "spoolman_connected": self.spoolman_connected,
                "influxdb_connected": self.influxdb_connected,
            }
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with APIs: {exception}")

    async def _fetch_spoolman_data(self) -> None:
        """Fetch data from Spoolman API."""
        if not self.spoolman_url:
            self.spoolman_connected = False
            return

        headers = {}
        if self.spoolman_token:
            headers["Authorization"] = f"Bearer {self.spoolman_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.spoolman_url}/api/v1/spool", headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        spools = {
                            str(spool["id"]): spool
                            for spool in data
                            if spool.get("active", True)
                        }
                        if self.spoolman_spool_ids:
                            self.spool_data = {
                                spool_id: spools[spool_id]
                                for spool_id in self.spoolman_spool_ids
                                if spool_id in spools
                            }
                        else:
                            self.spool_data = spools
                        self.spoolman_connected = True
                        _LOGGER.debug("Fetched %d active spools from Spoolman", len(self.spool_data))
                    else:
                        self.spoolman_connected = False
                        _LOGGER.error("Failed to fetch Spoolman data: %s", response.status)
        except Exception as e:
            self.spoolman_connected = False
            _LOGGER.error("Error fetching Spoolman data: %s", e)

    async def _fetch_shelly_energy_data(self) -> None:
        """Fetch energy data from Shelly entities."""
        # Fetch power entities
        for entity_id in self.shelly_power_entities:
            try:
                state = self.hass.states.get(entity_id)
                if state:
                    self.energy_data[entity_id] = {
                        "type": "power",
                        "value": float(state.state) if state.state != "unknown" else 0,
                        "unit": state.attributes.get("unit_of_measurement", "W"),
                        "timestamp": datetime.now().isoformat(),
                    }
                    _LOGGER.debug("Fetched power data for %s", entity_id)
            except Exception as e:
                _LOGGER.error("Failed to fetch power entity %s: %s", entity_id, e)

        # Fetch energy entities
        for entity_id in self.shelly_energy_entities:
            try:
                state = self.hass.states.get(entity_id)
                if state:
                    self.energy_data[entity_id] = {
                        "type": "energy",
                        "value": float(state.state) if state.state != "unknown" else 0,
                        "unit": state.attributes.get("unit_of_measurement", "kWh"),
                        "timestamp": datetime.now().isoformat(),
                    }
                    _LOGGER.debug("Fetched energy data for %s", entity_id)
            except Exception as e:
                _LOGGER.error("Failed to fetch energy entity %s: %s", entity_id, e)

    async def _fetch_ams_data(self) -> None:
        """Fetch AMS data."""
        for entity_id in self.ams_entities:
            try:
                state = self.hass.states.get(entity_id)
                if state:
                    self.ams_data[entity_id] = {
                        "value": state.state,
                        "attributes": state.attributes,
                        "timestamp": datetime.now().isoformat(),
                    }
                    _LOGGER.debug("Fetched AMS data for %s", entity_id)
            except Exception as e:
                _LOGGER.error("Failed to fetch AMS entity %s: %s", entity_id, e)

    async def _get_energy_cost_per_kwh(self) -> float:
        """Get current energy cost per kWh."""
        if self.energy_cost_source == "entity" and self.energy_cost_entity:
            try:
                state = self.hass.states.get(self.energy_cost_entity)
                if state and state.state != "unknown":
                    return float(state.state)
            except Exception as e:
                _LOGGER.error("Failed to get energy cost from entity %s: %s", self.energy_cost_entity, e)
        
        return self.energy_cost_per_kwh

    async def _fetch_influxdb_print_data(self) -> None:
        """Fetch print history from InfluxDB."""
        if not self.influxdb_client:
            self.influxdb_connected = False
            return

        query_api = self.influxdb_client.query_api()
        
        # Query print jobs from the last 30 days
        query = f'''
        from(bucket: "{self.influxdb_bucket}")
        |> range(start: -30d)
        |> filter(fn: (r) => r["_measurement"] == "print_job")
        '''
        if self.printer_name:
            query += f'|> filter(fn: (r) => r["printer"] == "{self.printer_name}")\n'
        query += '|> sort(columns: ["_time"], desc: true)\n'
        
        try:
            result = query_api.query(query)
            self.print_history = []
            
            for table in result:
                for record in table.records:
                    self.print_history.append({
                        "time": record.get_time(),
                        "printer": record.values.get("printer"),
                        "duration": record.values.get("duration"),
                        "material_used": record.values.get("material_used"),
                        "energy_consumed": record.values.get("energy_consumed"),
                        "spool_id": record.values.get("spool_id"),
                    })
            self.influxdb_connected = True
            _LOGGER.debug("Fetched %d print jobs from InfluxDB", len(self.print_history))
        except Exception as e:
            self.influxdb_connected = False
            _LOGGER.error("Failed to query InfluxDB: %s", e)

    async def _calculate_costs(self) -> None:
        """Calculate costs for each print job."""
        energy_cost_per_kwh = await self._get_energy_cost_per_kwh()
        
        for print_job in self.print_history:
            material_cost = 0
            energy_cost = 0
            
            # Calculate material cost using Spoolman data
            spool_id = print_job.get("spool_id")
            spool_id_str = str(spool_id) if spool_id is not None else None
            if spool_id_str and spool_id_str in self.spool_data:
                spool = self.spool_data[spool_id_str]
                material_used_g = print_job.get("material_used", 0)
                # Use price_per_kg from Spoolman if available, otherwise fallback to price
                price_per_kg = spool.get("price_per_kg")
                if price_per_kg:
                    material_cost = (material_used_g / 1000) * price_per_kg
                else:
                    # Fallback to price field (assuming it's per kg)
                    material_cost = (material_used_g / 1000) * spool.get("price", 0)
            
            # Calculate energy cost
            energy_consumed_kwh = print_job.get("energy_consumed", 0)
            energy_cost = energy_consumed_kwh * energy_cost_per_kwh
            
            print_job["material_cost"] = material_cost
            print_job["energy_cost"] = energy_cost
            print_job["total_cost"] = material_cost + energy_cost
            print_job["energy_cost_per_kwh"] = energy_cost_per_kwh

    def _calculate_total_cost(self) -> float:
        """Calculate total cost for all prints."""
        return sum(print_job.get("total_cost", 0) for print_job in self.print_history)

    async def async_add_print_job(
        self,
        printer_name: str,
        duration: float,
        material_used: float,
        spool_id: str,
        energy_consumed: float,
    ) -> None:
        """Add a new print job to the database."""
        if not self.influxdb_client:
            _LOGGER.error("InfluxDB client not initialized")
            return

        write_api = self.influxdb_client.write_api(write_options=SYNCHRONOUS)
        
        point = {
            "measurement": "print_job",
            "tags": {
                "printer": printer_name,
                "spool_id": spool_id,
            },
            "fields": {
                "duration": duration,
                "material_used": material_used,
                "energy_consumed": energy_consumed,
            },
            "time": datetime.utcnow().isoformat(),
        }
        
        try:
            write_api.write(bucket=self.influxdb_bucket, record=point)
            _LOGGER.info("Added print job for printer %s", printer_name)
            # Trigger an update to refresh the data
            await self.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to write print job to InfluxDB: %s", e)

    async def async_unload(self) -> None:
        """Unload resources."""
        if self.influxdb_client:
            self.influxdb_client.close()
            _LOGGER.info("InfluxDB client closed")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Print Cost Analyzer from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    store: Store = hass.data[DOMAIN].get(
        "store", Store(hass, GLOBAL_CONFIG_STORAGE_VERSION, GLOBAL_CONFIG_STORAGE_KEY)
    )
    hass.data[DOMAIN]["store"] = store
    global_config = await store.async_load() or {}
    hass.data[DOMAIN]["global"] = global_config

    coordinator = PrintCostCoordinator(hass, entry, global_config)
    await coordinator._async_setup()

    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
        await coordinator.async_unload()
        hass.data[DOMAIN]["entries"].pop(entry.entry_id)

    return unload_ok


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    store = Store(hass, GLOBAL_CONFIG_STORAGE_VERSION, GLOBAL_CONFIG_STORAGE_KEY)
    hass.data[DOMAIN]["store"] = store
    hass.data[DOMAIN]["global"] = await store.async_load() or {}
    hass.data[DOMAIN].setdefault("entries", {})
    await async_setup_services(hass)
    return True
