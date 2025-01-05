from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DOMAIN,
)

async def async_setup(hass: HomeAssistant, config: dict):
    session = async_get_clientsession(hass)
    hass.data[CONF_DOMAIN] = {
        "session": session
    }
    return True


async def async_setup_entry(hass: HomeAssistant, entry):
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True
