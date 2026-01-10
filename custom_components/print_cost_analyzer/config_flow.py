"""Config flow for Print Cost Analyzer integration."""
import logging
from typing import Any, Dict, Optional, List

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.storage import Store
from homeassistant.data_entry_flow import FlowResult

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
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Print Cost Analyzer."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._global_config: Dict[str, Any] = {}
        self._printer_name: Optional[str] = None
        self._spoolman_spool_ids: List[str] = []
        self._shelly_power_entities: List[str] = []
        self._shelly_energy_entities: List[str] = []
        self._ams_entities: List[str] = []

    def _get_store(self) -> Store:
        """Return the storage handler for global config."""
        return Store(self.hass, GLOBAL_CONFIG_STORAGE_VERSION, GLOBAL_CONFIG_STORAGE_KEY)

    async def _async_load_global_config(self) -> Dict[str, Any]:
        """Load global config from storage."""
        data = await self._get_store().async_load()
        return data or {}

    async def _async_save_global_config(self, data: Dict[str, Any]) -> None:
        """Save global config to storage."""
        await self._get_store().async_save(data)

    async def _async_fetch_spoolman_spools(self) -> List[Dict[str, Any]]:
        """Fetch spool list from Spoolman."""
        spoolman_url = self._global_config.get(CONF_SPOOLMAN_URL)
        if not spoolman_url:
            return []

        headers = {}
        spoolman_token = self._global_config.get(CONF_SPOOLMAN_TOKEN)
        if spoolman_token:
            headers["Authorization"] = f"Bearer {spoolman_token}"

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(f"{spoolman_url}/api/v1/spool", headers=headers) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch Spoolman spools: %s", response.status)
                    return []
                data = await response.json()
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch Spoolman spools: %s", err)
            return []

        spools: List[Dict[str, Any]] = []
        for spool in data:
            if spool.get("active", True):
                spools.append(spool)
        return spools

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self._global_config = {
                CONF_SPOOLMAN_URL: user_input[CONF_SPOOLMAN_URL],
                CONF_SPOOLMAN_TOKEN: user_input.get(CONF_SPOOLMAN_TOKEN),
                CONF_INFLUXDB_URL: user_input[CONF_INFLUXDB_URL],
                CONF_INFLUXDB_TOKEN: user_input[CONF_INFLUXDB_TOKEN],
                CONF_INFLUXDB_ORG: user_input[CONF_INFLUXDB_ORG],
                CONF_INFLUXDB_BUCKET: user_input[CONF_INFLUXDB_BUCKET],
            }

            return await self.async_step_energy_cost()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SPOOLMAN_URL): str,
                    vol.Optional(CONF_SPOOLMAN_TOKEN): str,
                    vol.Required(CONF_INFLUXDB_URL): str,
                    vol.Required(CONF_INFLUXDB_TOKEN): str,
                    vol.Required(CONF_INFLUXDB_ORG): str,
                    vol.Required(CONF_INFLUXDB_BUCKET): str,
                }
            ),
            errors=errors,
        )

    async def async_step_energy_cost(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle energy cost configuration."""
        if user_input is not None:
            energy_cost_source = user_input[CONF_ENERGY_COST_SOURCE]
            if energy_cost_source == "fixed":
                energy_cost_per_kwh = user_input[CONF_ENERGY_COST_PER_KWH]
                energy_cost_entity = None
            else:
                energy_cost_entity = user_input[CONF_ENERGY_COST_ENTITY]
                energy_cost_per_kwh = DEFAULT_ENERGY_COST_PER_KWH

            self._global_config.update(
                {
                    CONF_ENERGY_COST_SOURCE: energy_cost_source,
                    CONF_ENERGY_COST_PER_KWH: energy_cost_per_kwh,
                    CONF_ENERGY_COST_ENTITY: energy_cost_entity,
                }
            )
            await self._async_save_global_config(self._global_config)

            return await self.async_step_printer()

        # Get available energy price entities
        energy_price_entities = []
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            if state.attributes.get("unit_of_measurement") in [
                "€/kWh",
                "EUR/kWh",
                "€/kW",
                "EUR/kW",
            ] or "price" in entity_id.lower() or "cost" in entity_id.lower():
                energy_price_entities.append(entity_id)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENERGY_COST_SOURCE,
                    default="fixed",
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "fixed", "label": "Fester Preis"},
                            {"value": "entity", "label": "Entity"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        if energy_price_entities:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_ENERGY_COST_ENTITY,
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["sensor"],
                            include_entities=energy_price_entities,
                        )
                    )
                }
            )

        schema = schema.extend(
            {
                vol.Optional(
                    CONF_ENERGY_COST_PER_KWH,
                    default=DEFAULT_ENERGY_COST_PER_KWH,
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="energy_cost",
            data_schema=schema,
        )

    async def async_step_printer(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle per-printer configuration."""
        if user_input is not None:
            # Allow skipping printer setup if no name is provided
            if user_input.get(CONF_NAME):
                self._printer_name = user_input[CONF_NAME]
                self._spoolman_spool_ids = user_input.get(CONF_SPOOLMAN_SPOOL_IDS, [])
                self._shelly_power_entities = user_input.get(CONF_SHELLY_POWER_ENTITIES, [])
                self._shelly_energy_entities = user_input.get(CONF_SHELLY_ENERGY_ENTITIES, [])
                self._ams_entities = user_input.get(CONF_AMS_ENTITIES, [])
            return self._create_entry()

        if not self._global_config:
            self._global_config = await self._async_load_global_config()

        # Get available Shelly entities
        shelly_power_entities = []
        shelly_energy_entities = []
        
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            if "shelly" in entity_id.lower():
                if "power" in entity_id.lower() or state.attributes.get("unit_of_measurement") == "W":
                    shelly_power_entities.append(entity_id)
                elif "energy" in entity_id.lower() or state.attributes.get("unit_of_measurement") in ["kWh", "Wh"]:
                    shelly_energy_entities.append(entity_id)

        ams_entities = []
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            if "ams" in entity_id.lower() or "filament" in entity_id.lower():
                ams_entities.append(entity_id)

        spool_options = []
        for spool in await self._async_fetch_spoolman_spools():
            spool_id = str(spool.get("id"))
            label = spool.get("name") or spool.get("material", {}).get("name") or f"Spool {spool_id}"
            spool_options.append({"value": spool_id, "label": label})

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): str,
            }
        )

        if spool_options:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_SPOOLMAN_SPOOL_IDS,
                        default=[],
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=spool_options,
                            mode=SelectSelectorMode.DROPDOWN,
                            multiple=True,
                        )
                    ),
                }
            )

        return self.async_show_form(
            step_id="printer",
            data_schema=schema,
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self._printer_name or "3D Print Cost Analyzer",
            data={
                CONF_NAME: self._printer_name,
                CONF_SPOOLMAN_SPOOL_IDS: self._spoolman_spool_ids,
                CONF_SHELLY_POWER_ENTITIES: self._shelly_power_entities,
                CONF_SHELLY_ENERGY_ENTITIES: self._shelly_energy_entities,
                CONF_AMS_ENTITIES: self._ams_entities,
            },
        )


class PrintCostAnalyzerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Print Cost Analyzer."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = entry
        self._global_config: Dict[str, Any] = {}

    def _get_store(self) -> Store:
        """Return the storage handler for global config."""
        return Store(self.hass, GLOBAL_CONFIG_STORAGE_VERSION, GLOBAL_CONFIG_STORAGE_KEY)

    async def _async_load_global_config(self) -> Dict[str, Any]:
        """Load global config from storage."""
        data = await self._get_store().async_load()
        return data or {}

    async def _async_save_global_config(self, data: Dict[str, Any]) -> None:
        """Save global config to storage."""
        await self._get_store().async_save(data)

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the options flow."""
        if not self._global_config:
            self._global_config = await self._async_load_global_config()

        if user_input is not None:
            self._global_config = {
                CONF_SPOOLMAN_URL: user_input[CONF_SPOOLMAN_URL],
                CONF_SPOOLMAN_TOKEN: user_input.get(CONF_SPOOLMAN_TOKEN),
                CONF_INFLUXDB_URL: user_input[CONF_INFLUXDB_URL],
                CONF_INFLUXDB_TOKEN: user_input[CONF_INFLUXDB_TOKEN],
                CONF_INFLUXDB_ORG: user_input[CONF_INFLUXDB_ORG],
                CONF_INFLUXDB_BUCKET: user_input[CONF_INFLUXDB_BUCKET],
            }
            return await self.async_step_energy_cost()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SPOOLMAN_URL,
                        default=self._global_config.get(CONF_SPOOLMAN_URL, ""),
                    ): str,
                    vol.Optional(
                        CONF_SPOOLMAN_TOKEN,
                        default=self._global_config.get(CONF_SPOOLMAN_TOKEN, ""),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_URL,
                        default=self._global_config.get(CONF_INFLUXDB_URL, ""),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_TOKEN,
                        default=self._global_config.get(CONF_INFLUXDB_TOKEN, ""),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_ORG,
                        default=self._global_config.get(CONF_INFLUXDB_ORG, ""),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_BUCKET,
                        default=self._global_config.get(CONF_INFLUXDB_BUCKET, ""),
                    ): str,
                }
            ),
        )

    async def async_step_energy_cost(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle energy cost configuration."""
        if user_input is not None:
            energy_cost_source = user_input[CONF_ENERGY_COST_SOURCE]
            if energy_cost_source == "fixed":
                energy_cost_per_kwh = user_input[CONF_ENERGY_COST_PER_KWH]
                energy_cost_entity = None
            else:
                energy_cost_entity = user_input[CONF_ENERGY_COST_ENTITY]
                energy_cost_per_kwh = DEFAULT_ENERGY_COST_PER_KWH

            self._global_config.update(
                {
                    CONF_ENERGY_COST_SOURCE: energy_cost_source,
                    CONF_ENERGY_COST_PER_KWH: energy_cost_per_kwh,
                    CONF_ENERGY_COST_ENTITY: energy_cost_entity,
                }
            )
            await self._async_save_global_config(self._global_config)
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN]["global"] = self._global_config

            for coordinator in self.hass.data[DOMAIN].get("entries", {}).values():
                coordinator.spoolman_url = self._global_config.get(CONF_SPOOLMAN_URL)
                coordinator.spoolman_token = self._global_config.get(CONF_SPOOLMAN_TOKEN)
                coordinator.influxdb_url = self._global_config.get(CONF_INFLUXDB_URL)
                coordinator.influxdb_token = self._global_config.get(CONF_INFLUXDB_TOKEN)
                coordinator.influxdb_org = self._global_config.get(CONF_INFLUXDB_ORG)
                coordinator.influxdb_bucket = self._global_config.get(CONF_INFLUXDB_BUCKET)
                coordinator.energy_cost_source = self._global_config.get(
                    CONF_ENERGY_COST_SOURCE, "fixed"
                )
                coordinator.energy_cost_per_kwh = self._global_config.get(
                    CONF_ENERGY_COST_PER_KWH, DEFAULT_ENERGY_COST_PER_KWH
                )
                coordinator.energy_cost_entity = self._global_config.get(CONF_ENERGY_COST_ENTITY)
                await coordinator.async_request_refresh()

            return self.async_create_entry(title="", data={})

        # Get available energy price entities
        energy_price_entities = []
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            if state.attributes.get("unit_of_measurement") in [
                "€/kWh",
                "EUR/kWh",
                "€/kW",
                "EUR/kW",
            ] or "price" in entity_id.lower() or "cost" in entity_id.lower():
                energy_price_entities.append(entity_id)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENERGY_COST_SOURCE,
                    default=self._global_config.get(CONF_ENERGY_COST_SOURCE, "fixed"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "fixed", "label": "Fester Preis"},
                            {"value": "entity", "label": "Entity"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        if energy_price_entities:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_ENERGY_COST_ENTITY,
                        default=self._global_config.get(CONF_ENERGY_COST_ENTITY, ""),
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["sensor"],
                            include_entities=energy_price_entities,
                        )
                    )
                }
            )

        schema = schema.extend(
            {
                vol.Optional(
                    CONF_ENERGY_COST_PER_KWH,
                    default=self._global_config.get(
                        CONF_ENERGY_COST_PER_KWH, DEFAULT_ENERGY_COST_PER_KWH
                    ),
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="energy_cost",
            data_schema=schema,
        )


async def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> config_entries.OptionsFlow:
    """Return the options flow handler."""
    return PrintCostAnalyzerOptionsFlow(config_entry)
