"""Services for Print Cost Analyzer integration."""
import logging
from typing import Dict, Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.config_validation import make_entity_service_schema

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_PRINT_JOB_SCHEMA = make_entity_service_schema(
    {
        vol.Required("printer"): str,
        vol.Required("duration"): vol.Coerce(float),
        vol.Required("material_used"): vol.Coerce(float),
        vol.Required("spool_id"): str,
        vol.Required("energy_consumed"): vol.Coerce(float),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Print Cost Analyzer integration."""

    async def add_print_job_service(call: ServiceCall) -> None:
        """Handle the add print job service call."""
        printer = call.data["printer"]
        duration = call.data["duration"]
        material_used = call.data["material_used"]
        spool_id = call.data["spool_id"]
        energy_consumed = call.data["energy_consumed"]

        _LOGGER.info(
            "Adding print job: printer=%s, duration=%s, material_used=%s, spool_id=%s, energy_consumed=%s",
            printer,
            duration,
            material_used,
            spool_id,
            energy_consumed,
        )

        # Find the coordinator and add the print job
        for entry_id, coordinator in hass.data[DOMAIN].items():
            await coordinator.async_add_print_job(
                printer, duration, material_used, spool_id, energy_consumed
            )

    hass.services.async_register(
        DOMAIN,
        "add_print_job",
        add_print_job_service,
        schema=SERVICE_ADD_PRINT_JOB_SCHEMA,
    )