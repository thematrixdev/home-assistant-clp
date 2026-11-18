import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _async_cleanup_orphaned_devices(hass: HomeAssistant, entry_id: str) -> None:
    """Remove any devices belonging to this config entry that have no entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, entry_id)
    for dev in devices:
        entities = er.async_entries_for_device(ent_reg, dev.id)
        if not entities:
            _LOGGER.info(
                "Removing orphaned CLP device without entities: %s (id: %s)",
                dev.name,
                dev.id,
            )
            dev_reg.async_remove_device(dev.id)


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
    await _async_cleanup_orphaned_devices(hass, entry.entry_id)
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
