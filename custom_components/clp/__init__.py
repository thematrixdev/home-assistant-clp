from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DOMAIN,
)

DOMAIN = CONF_DOMAIN


async def async_setup(hass: HomeAssistant, config: dict):
    session = async_get_clientsession(hass)
    hass.data[DOMAIN] = {
        "session": session
    }
    return True


async def async_setup_entry(hass: HomeAssistant, entry):
    session = async_get_clientsession(hass)
    hass.data[DOMAIN] = {
        "session": session
    }
    return True
