import asyncio
import logging

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def verify_otp(session, email, otp, timeout=30):
    """Verify OTP and return token data or raise exception."""
    url = "https://api.clp.com.hk/ts1/ms/profile/accountManagement/passwordlesslogin/otpverify"
    json_payload = {
        "type": "email",
        "email": email,
        "otp": otp,
    }
    try:
        async with async_timeout.timeout(timeout):
            async with session.post(url, json=json_payload) as response:
                response.raise_for_status()
                data = await response.json()
                if not data or 'data' not in data:
                    raise ValueError('Invalid response data')
                _LOGGER.debug(f"OTP verification response: {data}")
                return data['data']
    except Exception as ex:
        _LOGGER.error(f"OTP verification failed: {ex}")
        raise

async def async_setup(hass: HomeAssistant, config: dict):
    session = async_get_clientsession(hass)
    hass.data[CONF_DOMAIN] = {
        "session": session
    }
    return True


async def async_setup_entry(hass: HomeAssistant, entry):
    if CONF_DOMAIN not in hass.data:
        session = async_get_clientsession(hass)
        hass.data[CONF_DOMAIN] = {
            "session": session,
            "access_token": entry.data.get("access_token"),
            "refresh_token": entry.data.get("refresh_token"),
            "access_token_expiry_time": entry.data.get("access_token_expiry_time"),
            "token_lock": asyncio.Lock(),
        }
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True
