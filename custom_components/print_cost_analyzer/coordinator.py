"""Update coordinator for Print Cost Analyzer integration."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import aiohttp
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SPOOLMAN_URL,
    CONF_SPOOLMAN_TOKEN,
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

_LOGGER = logging.getLogger(__name__)


class PrintCostDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the APIs."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]) -> None:
        """Initialize."""
        self.hass = hass
        self.config = config
        self.spoolman_url = config[CONF_SPOOLMAN_URL]
        self.spoolman_token = config.get(CONF_SPOOLMAN_TOKEN)
        self.shelly_power_entities = config.get(CONF_SHELLY_POWER_ENTITIES, [])
        self.shelly_energy_entities = config.get(CONF_SHELLY_ENERGY_ENTITIES, [])
        self.ams_entities = config.get(CONF_AMS_ENTITIES, [])
        self.influxdb_url = config[CONF_INFLUXDB_URL]
        self.influxdb_token = config[CONF_INFLUXDB_TOKEN]
        self.influxdb_org = config[CONF_INFLUXDB_ORG]
        self.influxdb_bucket = config[CONF_INFLUXDB_BUCKET]
        self.energy_cost_source = config.get(CONF_ENERGY_COST_SOURCE, "fixed")
        self.energy_cost_per_kwh = config.get(
            CONF_ENERGY_COST_PER_KWH, DEFAULT_ENERGY_COST_PER_KWH
        )
        self.energy_cost_entity = config.get(CONF_ENERGY_COST_ENTITY)

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
            name="print_cost_analyzer",
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
                        self.spool_data = {
                            str(spool["id"]): spool
                            for spool in data
                            if spool.get("active", True)
                        }
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
        |> sort(columns: ["_time"], desc: true)
        '''
        
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
            if spool_id and spool_id in self.spool_data:
                spool = self.spool_data[spool_id]
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