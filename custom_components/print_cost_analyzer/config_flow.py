"""Config and options flow for the 3D Print Cost Analyzer."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ENERGY, CONF_PRICE_ENTITY, CONF_PRINTERS, CONF_SETTLE_MINUTES,
    DEFAULT_PRICE_ENTITY, DEFAULT_SETTLE_MINUTES, DOMAIN, UID_STATUS,
)


def _status_entities(hass: HomeAssistant) -> list[str]:
    """Every ha-bambulab print-status entity."""
    return sorted(
        e.entity_id for e in er.async_get(hass).entities.values()
        if e.platform == "bambu_lab" and e.unique_id.endswith(UID_STATUS)
    )


def _guess_energy(hass: HomeAssistant, status_entity: str) -> str | None:
    """Pick the power meter whose name mentions the printer, e.g. 'Shelly H2D'."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(status_entity)
    device = dr.async_get(hass).async_get(entry.device_id) if entry and entry.device_id else None
    key = ((device.name_by_user or device.name) if device else "").lower().split("_")[0]
    if not key:
        return None
    for st in hass.states.async_all("sensor"):
        if st.attributes.get("device_class") != "energy":
            continue
        label = f"{st.entity_id} {st.attributes.get('friendly_name', '')}".lower()
        if key in label:
            return st.entity_id
    return None


def _general_schema(hass: HomeAssistant, current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PRINTERS, default=current.get(CONF_PRINTERS, _status_entities(hass))):
            selector.EntitySelector(selector.EntitySelectorConfig(
                domain="sensor", integration="bambu_lab", multiple=True)),
        vol.Required(CONF_PRICE_ENTITY, default=current.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_number", "sensor", "number"])),
        vol.Required(CONF_SETTLE_MINUTES, default=current.get(CONF_SETTLE_MINUTES, DEFAULT_SETTLE_MINUTES)):
            selector.NumberSelector(selector.NumberSelectorConfig(
                min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)),
    })


def _energy_schema(hass: HomeAssistant, printers: list[str], current: dict[str, str]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for eid in printers:
        default = current.get(eid) or _guess_energy(hass, eid)
        key = vol.Optional(eid, description={"suggested_value": default}) if default else vol.Optional(eid)
        fields[key] = selector.EntitySelector(selector.EntitySelectorConfig(
            domain="sensor", device_class="energy"))
    return vol.Schema(fields)


class PrintCostConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            self._data = dict(user_input)
            return await self.async_step_energy()
        return self.async_show_form(step_id="user", data_schema=_general_schema(self.hass, {}))

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_ENERGY] = {k: v for k, v in user_input.items() if v}
            return self.async_create_entry(title="3D-Druckkosten", data=self._data)
        return self.async_show_form(
            step_id="energy", data_schema=_energy_schema(self.hass, self._data[CONF_PRINTERS], {}))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return PrintCostOptionsFlow()


class PrintCostOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = dict(user_input)
            return await self.async_step_energy()
        return self.async_show_form(step_id="init", data_schema=_general_schema(self.hass, self._current()))

    async def async_step_energy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_ENERGY] = {k: v for k, v in user_input.items() if v}
            return self.async_create_entry(data=self._data)
        return self.async_show_form(step_id="energy", data_schema=_energy_schema(
            self.hass, self._data[CONF_PRINTERS], self._current().get(CONF_ENERGY, {})))
