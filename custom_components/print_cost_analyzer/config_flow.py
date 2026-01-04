"""Config flow for Print Cost Analyzer integration."""
import logging
from typing import Any, Dict, Optional, List

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_URL,
    CONF_TOKEN,
    CONF_NAME,
)
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
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
)

_LOGGER = logging.getLogger(__name__)


class PrintCostAnalyzerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Print Cost Analyzer."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._spoolman_url: Optional[str] = None
        self._spoolman_token: Optional[str] = None
        self._influxdb_url: Optional[str] = None
        self._influxdb_token: Optional[str] = None
        self._influxdb_org: Optional[str] = None
        self._influxdb_bucket: Optional[str] = None
        self._shelly_power_entities: List[str] = []
        self._shelly_energy_entities: List[str] = []
        self._ams_entities: List[str] = []
        self._energy_cost_source: str = "fixed"
        self._energy_cost_per_kwh: float = DEFAULT_ENERGY_COST_PER_KWH
        self._energy_cost_entity: Optional[str] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self._spoolman_url = user_input[CONF_SPOOLMAN_URL]
            self._spoolman_token = user_input.get(CONF_SPOOLMAN_TOKEN)
            self._influxdb_url = user_input[CONF_INFLUXDB_URL]
            self._influxdb_token = user_input[CONF_INFLUXDB_TOKEN]
            self._influxdb_org = user_input[CONF_INFLUXDB_ORG]
            self._influxdb_bucket = user_input[CONF_INFLUXDB_BUCKET]

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
            self._energy_cost_source = user_input[CONF_ENERGY_COST_SOURCE]
            if self._energy_cost_source == "fixed":
                self._energy_cost_per_kwh = user_input[CONF_ENERGY_COST_PER_KWH]
                self._energy_cost_entity = None
            else:
                self._energy_cost_entity = user_input[CONF_ENERGY_COST_ENTITY]
                self._energy_cost_per_kwh = DEFAULT_ENERGY_COST_PER_KWH

            return await self.async_step_shelly_entities()

        # Get available energy price entities
        energy_price_entities = []
        for entity_id, entity in self.hass.states.async_all():
            if entity.attributes.get("unit_of_measurement") in [
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
                            entity=energy_price_entities,
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

    async def async_step_shelly_entities(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle Shelly entities selection."""
        if user_input is not None:
            self._shelly_power_entities = user_input.get(CONF_SHELLY_POWER_ENTITIES, [])
            self._shelly_energy_entities = user_input.get(CONF_SHELLY_ENERGY_ENTITIES, [])
            return await self.async_step_ams_entities()

        # Get available Shelly entities
        shelly_power_entities = []
        shelly_energy_entities = []
        
        for entity_id, entity in self.hass.states.async_all():
            if "shelly" in entity_id.lower():
                if "power" in entity_id.lower() or entity.attributes.get("unit_of_measurement") == "W":
                    shelly_power_entities.append(entity_id)
                elif "energy" in entity_id.lower() or entity.attributes.get("unit_of_measurement") in ["kWh", "Wh"]:
                    shelly_energy_entities.append(entity_id)

        return self.async_show_form(
            step_id="shelly_entities",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SHELLY_POWER_ENTITIES,
                        default=shelly_power_entities,
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["sensor"],
                            entity=shelly_power_entities,
                            multiple=True,
                        )
                    ),
                    vol.Optional(
                        CONF_SHELLY_ENERGY_ENTITIES,
                        default=shelly_energy_entities,
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["sensor"],
                            entity=shelly_energy_entities,
                            multiple=True,
                        )
                    ),
                }
            ),
        )

    async def async_step_ams_entities(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle AMS entities selection."""
        if user_input is not None:
            self._ams_entities = user_input.get(CONF_AMS_ENTITIES, [])
            return self._create_entry()

        # Get available AMS entities
        ams_entities = []
        for entity_id, entity in self.hass.states.async_all():
            if "ams" in entity_id.lower() or "filament" in entity_id.lower():
                ams_entities.append(entity_id)

        return self.async_show_form(
            step_id="ams_entities",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AMS_ENTITIES,
                        default=ams_entities,
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["sensor"],
                            entity=ams_entities,
                            multiple=True,
                        )
                    ),
                }
            ),
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title="3D Print Cost Analyzer",
            data={
                CONF_SPOOLMAN_URL: self._spoolman_url,
                CONF_SPOOLMAN_TOKEN: self._spoolman_token,
                CONF_SHELLY_POWER_ENTITIES: self._shelly_power_entities,
                CONF_SHELLY_ENERGY_ENTITIES: self._shelly_energy_entities,
                CONF_AMS_ENTITIES: self._ams_entities,
                CONF_INFLUXDB_URL: self._influxdb_url,
                CONF_INFLUXDB_TOKEN: self._influxdb_token,
                CONF_INFLUXDB_ORG: self._influxdb_org,
                CONF_INFLUXDB_BUCKET: self._influxdb_bucket,
                CONF_ENERGY_COST_SOURCE: self._energy_cost_source,
                CONF_ENERGY_COST_PER_KWH: self._energy_cost_per_kwh,
                CONF_ENERGY_COST_ENTITY: self._energy_cost_entity,
            },
        )