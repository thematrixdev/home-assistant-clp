"""Config flow for CLP integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TIMEOUT,
    CONF_USERNAME,
    CONF_TYPE,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
)

from .const import (
    CONF_DOMAIN,
    CONF_GET_ACCT,
    CONF_GET_BILL,
    CONF_GET_BIMONTHLY,
    CONF_GET_DAILY,
    CONF_GET_ESTIMATION,
    CONF_GET_HOURLY,
    CONF_GET_HOURLY_DAYS,
    CONF_RETRY_DELAY,
    CONF_RES_ENABLE,
    CONF_RES_GET_BILL,
    CONF_RES_GET_DAILY,
    CONF_RES_GET_HOURLY,
    CONF_RES_GET_HOURLY_DAYS,
    CONF_RES_NAME,
    CONF_RES_TYPE,
)

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain="clphk"):
    """Handle a config flow for CLP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
            except Exception as ex:
                _LOGGER.exception(ex)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default="CLP",
                    ): TextSelector(TextSelectorConfig()),
                    vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig()),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type="password")
                    ),
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=30,
                    ): NumberSelector(NumberSelectorConfig(min=1, max=120, mode=NumberSelectorMode.BOX)),
                    vol.Optional(
                        CONF_RETRY_DELAY,
                        default=300,
                    ): NumberSelector(NumberSelectorConfig(min=60, max=3600, mode=NumberSelectorMode.BOX)),
                    vol.Optional(CONF_TYPE, default=""): TextSelector(TextSelectorConfig()),
                    vol.Optional(CONF_GET_ACCT, default=False): BooleanSelector(),
                    vol.Optional(CONF_GET_BILL, default=False): BooleanSelector(),
                    vol.Optional(CONF_GET_ESTIMATION, default=False): BooleanSelector(),
                    vol.Optional(CONF_GET_BIMONTHLY, default=False): BooleanSelector(),
                    vol.Optional(CONF_GET_DAILY, default=False): BooleanSelector(),
                    vol.Optional(CONF_GET_HOURLY, default=False): BooleanSelector(),
                    vol.Optional(
                        CONF_GET_HOURLY_DAYS,
                        default=1,
                    ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
                    vol.Optional(CONF_RES_ENABLE, default=False): BooleanSelector(),
                    vol.Optional(
                        CONF_RES_NAME,
                        default="CLP Renewable Energy",
                    ): TextSelector(TextSelectorConfig()),
                    vol.Optional(CONF_RES_TYPE, default=""): TextSelector(TextSelectorConfig()),
                    vol.Optional(CONF_RES_GET_BILL, default=False): BooleanSelector(),
                    vol.Optional(CONF_RES_GET_DAILY, default=False): BooleanSelector(),
                    vol.Optional(CONF_RES_GET_HOURLY, default=False): BooleanSelector(),
                    vol.Optional(
                        CONF_RES_GET_HOURLY_DAYS,
                        default=1,
                    ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
                }
            ),
            errors=errors,
        ) 