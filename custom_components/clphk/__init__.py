import asyncio
import base64
import logging

import aiohttp
import async_timeout
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CLP_PUBLIC_KEY,
    CONF_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

API_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://www.clp.com.hk/",
    "Content-Type": "application/json",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

async def request_otp(session, email, timeout=30):
    """Request OTP for an email address."""
    url = "https://api.clp.com.hk/ts1/ms/profile/register/eligibilityCheckAndLogin"
    public_key = serialization.load_pem_public_key(CONF_CLP_PUBLIC_KEY.encode())
    json_payload = {
        "email": base64.b64encode(public_key.encrypt(
            email.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )).decode(),
        "phone": "",
        "type": base64.b64encode(public_key.encrypt(
            "email".encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )).decode(),
    }
    try:
        async with async_timeout.timeout(timeout):
            async with session.post(url, json=json_payload, headers=API_DEFAULT_HEADERS) as response:
                response.raise_for_status()
                data = await response.json()
                if not data or "data" not in data:
                    raise ValueError("Invalid OTP request response data")
                _LOGGER.debug("OTP request response: %s", data)
                return data["data"]
    except Exception as ex:
        _LOGGER.error("OTP request failed: %s", ex)
        raise

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
            async with session.post(url, json=json_payload, headers=API_DEFAULT_HEADERS) as response:
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

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok and CONF_DOMAIN in hass.data:
        hass.data.pop(CONF_DOMAIN)
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry):
    """Reload config entry when options or data change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
