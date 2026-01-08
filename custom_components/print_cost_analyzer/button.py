"""Button platform for Print Cost Analyzer integration."""
import logging
from typing import Dict, Any

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AddPrintJobButton(CoordinatorEntity, ButtonEntity):
    """Button to manually add a print job."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        printer_name = entry.data.get(CONF_NAME) or entry.title or "3D Print Cost Analyzer"
        self._attr_name = f"{printer_name} Add Print Job"
        self._attr_unique_id = f"{entry.entry_id}_add_print_job"
        self._attr_device_class = ButtonDeviceClass.UPDATE
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{printer_name} Print Cost Analyzer",
            manufacturer="Custom",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        # This would typically trigger a service call or flow
        # For now, we'll just log the action
        _LOGGER.info("Add Print Job button pressed")
        
        # Example: You could trigger a service call here
        # await self.hass.services.async_call(
        #     DOMAIN, "add_print_job", {"printer": "Ender3", "duration": 3600}
        # )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Print Cost Analyzer buttons based on a config entry."""
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]

    entities = [
        AddPrintJobButton(coordinator, entry),
    ]

    async_add_entities(entities)
