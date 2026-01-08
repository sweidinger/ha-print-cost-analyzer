"""Sensor platform for Print Cost Analyzer integration."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PrintCostSensor(CoordinatorEntity, SensorEntity):
    """Base class for Print Cost Analyzer sensors."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        name: str,
        unique_id: str,
        device_class: Optional[str] = None,
        state_class: Optional[str] = None,
        unit: Optional[str] = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        printer_name = entry.data.get(CONF_NAME) or entry.title or "3D Print Cost Analyzer"
        self._attr_name = f"{printer_name} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{unique_id}"
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{printer_name} Print Cost Analyzer",
            manufacturer="Custom",
        )


class TotalCostSensor(PrintCostSensor):
    """Sensor for total print cost."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "Total Print Cost",
            "total_cost",
            SensorDeviceClass.MONETARY,
            SensorStateClass.TOTAL,
            "EUR",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the total cost."""
        return self.coordinator.data.get("total_cost") if self.coordinator.data else None


class ActiveSpoolsSensor(PrintCostSensor):
    """Sensor for number of active spools."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "Active Spools",
            "active_spools",
            None,
            None,
            "spools",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return the number of active spools."""
        if not self.coordinator.data:
            return None
        return len(self.coordinator.data.get("spools", {}))


class TotalPrintsSensor(PrintCostSensor):
    """Sensor for total number of prints."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "Total Prints",
            "total_prints",
            None,
            SensorStateClass.TOTAL_INCREASING,
            "prints",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return the total number of prints."""
        if not self.coordinator.data:
            return None
        return len(self.coordinator.data.get("print_history", []))


class ShellyPowerSensor(PrintCostSensor):
    """Sensor for Shelly plug power consumption."""

    def __init__(self, coordinator, entry: ConfigEntry, entity_id: str) -> None:
        """Initialize the sensor."""
        # Extract friendly name from entity_id
        friendly_name = entity_id.split(".")[-1].replace("_", " ").title()
        super().__init__(
            coordinator,
            entry,
            f"Shelly {friendly_name} Power",
            f"shelly_{entity_id.replace('.', '_')}_power",
            SensorDeviceClass.POWER,
            SensorStateClass.MEASUREMENT,
            UnitOfPower.WATT,
        )
        self._entity_id = entity_id

    @property
    def native_value(self) -> Optional[float]:
        """Return the current power consumption."""
        if not self.coordinator.data:
            return None
        energy_data = self.coordinator.data.get("energy", {})
        entity_data = energy_data.get(self._entity_id, {})
        return entity_data.get("value") if entity_data.get("type") == "power" else None


class ShellyEnergySensor(PrintCostSensor):
    """Sensor for Shelly plug total energy consumption."""

    def __init__(self, coordinator, entry: ConfigEntry, entity_id: str) -> None:
        """Initialize the sensor."""
        # Extract friendly name from entity_id
        friendly_name = entity_id.split(".")[-1].replace("_", " ").title()
        super().__init__(
            coordinator,
            entry,
            f"Shelly {friendly_name} Energy",
            f"shelly_{entity_id.replace('.', '_')}_energy",
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL_INCREASING,
            UnitOfEnergy.KILO_WATT_HOUR,
        )
        self._entity_id = entity_id

    @property
    def native_value(self) -> Optional[float]:
        """Return the total energy consumption."""
        if not self.coordinator.data:
            return None
        energy_data = self.coordinator.data.get("energy", {})
        entity_data = energy_data.get(self._entity_id, {})
        return entity_data.get("value") if entity_data.get("type") == "energy" else None


class AMSSensor(PrintCostSensor):
    """Sensor for AMS units."""

    def __init__(self, coordinator, entry: ConfigEntry, entity_id: str) -> None:
        """Initialize the sensor."""
        # Extract friendly name from entity_id
        friendly_name = entity_id.split(".")[-1].replace("_", " ").title()
        super().__init__(
            coordinator,
            entry,
            f"AMS {friendly_name}",
            f"ams_{entity_id.replace('.', '_')}",
            None,
            None,
            None,
        )
        self._entity_id = entity_id

    @property
    def native_value(self) -> Optional[str]:
        """Return the AMS value."""
        if not self.coordinator.data:
            return None
        ams_data = self.coordinator.data.get("ams", {})
        entity_data = ams_data.get(self._entity_id, {})
        return entity_data.get("value")

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return additional attributes."""
        if not self.coordinator.data:
            return None
        ams_data = self.coordinator.data.get("ams", {})
        entity_data = ams_data.get(self._entity_id, {})
        return entity_data.get("attributes", {})


class EnergyCostSensor(PrintCostSensor):
    """Sensor for current energy cost per kWh."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            "Energy Cost per kWh",
            "energy_cost_per_kwh",
            SensorDeviceClass.MONETARY,
            SensorStateClass.MEASUREMENT,
            "EUR",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current energy cost per kWh."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("energy_cost_per_kwh")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Print Cost Analyzer sensors based on a config entry."""
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]

    entities = [
        TotalCostSensor(coordinator, entry),
        ActiveSpoolsSensor(coordinator, entry),
        TotalPrintsSensor(coordinator, entry),
        EnergyCostSensor(coordinator, entry),
    ]

    # Add sensors for each Shelly power entity
    shelly_power_entities = entry.data.get("shelly_power_entities", [])
    for entity_id in shelly_power_entities:
        entities.append(ShellyPowerSensor(coordinator, entry, entity_id))

    # Add sensors for each Shelly energy entity
    shelly_energy_entities = entry.data.get("shelly_energy_entities", [])
    for entity_id in shelly_energy_entities:
        entities.append(ShellyEnergySensor(coordinator, entry, entity_id))

    # Add sensors for each AMS entity
    ams_entities = entry.data.get("ams_entities", [])
    for entity_id in ams_entities:
        entities.append(AMSSensor(coordinator, entry, entity_id))

    async_add_entities(entities)
