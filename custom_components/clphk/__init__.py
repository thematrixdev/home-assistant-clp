import asyncio

from homeassistant.core import HomeAssistant

from .const import (
    CONF_DOMAIN,
)


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data[CONF_DOMAIN] = {}

    async def handle_refresh_tariff(call):
        sensors = hass.data.get(CONF_DOMAIN, {}).get("sensors", [])
        for sensor in sensors:
            if hasattr(sensor, "async_fetch_monthly_tariff"):
                await sensor.async_fetch_monthly_tariff(force=True)
                sensor.async_write_ha_state()
                for sub in getattr(sensor, "_sub_sensors", []):
                    if getattr(sub, "hass", None):
                        sub.async_write_ha_state()

    hass.services.async_register(CONF_DOMAIN, "refresh_tariff", handle_refresh_tariff)
    return True


async def async_setup_entry(hass: HomeAssistant, entry):
    if CONF_DOMAIN not in hass.data:
        hass.data[CONF_DOMAIN] = {
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
