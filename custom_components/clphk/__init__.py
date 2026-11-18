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
    hass.data.setdefault(CONF_DOMAIN, {})

    async def handle_refresh_tariff(call):
        for entry_data in hass.data.get(CONF_DOMAIN, {}).values():
            if isinstance(entry_data, dict):
                sensors = entry_data.get("sensors", [])
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
    hass.data.setdefault(CONF_DOMAIN, {})
    hass.data[CONF_DOMAIN][entry.entry_id] = {
        "access_token": entry.data.get("access_token"),
        "refresh_token": entry.data.get("refresh_token"),
        "access_token_expiry_time": entry.data.get("access_token_expiry_time"),
        "token_lock": asyncio.Lock(),
        "sensors": [],
    }
    # Keep top-level keys for backwards compatibility with any external calls
    hass.data[CONF_DOMAIN]["access_token"] = entry.data.get("access_token")
    hass.data[CONF_DOMAIN]["refresh_token"] = entry.data.get("refresh_token")
    hass.data[CONF_DOMAIN]["access_token_expiry_time"] = entry.data.get("access_token_expiry_time")
    hass.data[CONF_DOMAIN]["token_lock"] = hass.data[CONF_DOMAIN][entry.entry_id]["token_lock"]

    # Register update listener so options flow updates take effect immediately
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    await _async_cleanup_orphaned_devices(hass, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok and CONF_DOMAIN in hass.data:
        hass.data[CONF_DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry):
    """Reload config entry when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
