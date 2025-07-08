"""Config flow for CLP integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_NAME,
    CONF_TIMEOUT,
    CONF_TYPE,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import config_entry_flow
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
)

from . import verify_otp
from .const import (
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

class CLPHKOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle CLPHK options flow for reconfiguring all values."""
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._user_input = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        _LOGGER.debug(f"[CFG] async_step_init called with user_input={user_input}")
        errors = {}
        data = {**self.config_entry.data, **self._user_input}
        if user_input is not None:
            email = user_input.get("email_address")
            otp = user_input.get("otp")
            timeout = user_input.get("timeout", 30)
            session = aiohttp_client.async_get_clientsession(self.hass)
            try:
                _LOGGER.debug(f"[CFG] Verifying OTP for email={email}, otp={otp}, timeout={timeout}")
                token_data = await verify_otp(session, email, otp, timeout)
                _LOGGER.debug(f"[CFG] OTP verification returned token_data={token_data}")
                user_input["access_token"] = token_data["access_token"]
                user_input["refresh_token"] = token_data["refresh_token"]
                user_input["access_token_expiry_time"] = token_data.get("expires_in")
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **user_input},
                )
                _LOGGER.debug(f"[CFG] Updated config entry with new tokens, triggering reload.")
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title=self.config_entry.title, data=user_input)
            except Exception as ex:
                _LOGGER.exception(f"[CFG] OTP verification or config update failed: {ex}")
                errors["base"] = "auth_failed"
        _LOGGER.debug(f"[CFG] Showing config form with data={data} errors={errors}")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_NAME,
                    default=data.get(CONF_NAME, "CLP"),
                ): TextSelector(TextSelectorConfig()),
                vol.Required("email_address", default=data.get("email_address", "")): TextSelector(TextSelectorConfig()),
                vol.Required("otp", default=data.get("otp", "")): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_TIMEOUT,
                    default=data.get(CONF_TIMEOUT, 30),
                ): NumberSelector(NumberSelectorConfig(min=1, max=120, mode=NumberSelectorMode.BOX)),
                vol.Optional(
                    CONF_RETRY_DELAY,
                    default=data.get(CONF_RETRY_DELAY, 300),
                ): NumberSelector(NumberSelectorConfig(min=60, max=3600, mode=NumberSelectorMode.BOX)),
                vol.Optional(CONF_TYPE, default=data.get(CONF_TYPE, "")): TextSelector(TextSelectorConfig()),
                vol.Optional(CONF_GET_ACCT, default=data.get(CONF_GET_ACCT, False)): BooleanSelector(),
                vol.Optional(CONF_GET_BILL, default=data.get(CONF_GET_BILL, False)): BooleanSelector(),
                vol.Optional(CONF_GET_ESTIMATION, default=data.get(CONF_GET_ESTIMATION, False)): BooleanSelector(),
                vol.Optional(CONF_GET_BIMONTHLY, default=data.get(CONF_GET_BIMONTHLY, False)): BooleanSelector(),
                vol.Optional(CONF_GET_DAILY, default=data.get(CONF_GET_DAILY, False)): BooleanSelector(),
                vol.Optional(CONF_GET_HOURLY, default=data.get(CONF_GET_HOURLY, False)): BooleanSelector(),
                vol.Optional(
                    CONF_GET_HOURLY_DAYS,
                    default=data.get(CONF_GET_HOURLY_DAYS, 1),
                ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
                vol.Optional(CONF_RES_ENABLE, default=data.get(CONF_RES_ENABLE, False)): BooleanSelector(),
                vol.Optional(
                    CONF_RES_NAME,
                    default=data.get(CONF_RES_NAME, "CLP Renewable Energy"),
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(CONF_RES_TYPE, default=data.get(CONF_RES_TYPE, "")): TextSelector(TextSelectorConfig()),
                vol.Optional(CONF_RES_GET_BILL, default=data.get(CONF_RES_GET_BILL, False)): BooleanSelector(),
                vol.Optional(CONF_RES_GET_DAILY, default=data.get(CONF_RES_GET_DAILY, False)): BooleanSelector(),
                vol.Optional(CONF_RES_GET_HOURLY, default=data.get(CONF_RES_GET_HOURLY, False)): BooleanSelector(),
                vol.Optional(
                    CONF_RES_GET_HOURLY_DAYS,
                    default=data.get(CONF_RES_GET_HOURLY_DAYS, 1),
                ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
            }),
            errors=errors,
        )

class ConfigFlow(config_entries.ConfigFlow, domain="clphk"):
    """Handle a config flow for CLP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # OTP verification logic
            email = user_input.get("email")
            otp = user_input.get("otp")
            timeout = user_input.get("timeout", 30)
            session = aiohttp_client.async_get_clientsession(self.hass)
            try:
                token_data = await verify_otp(session, email, otp, timeout)
                _LOGGER.debug(token_data)

                user_input["access_token"] = token_data["access_token"]
                user_input["refresh_token"] = token_data["refresh_token"]
                user_input["access_token_expiry_time"] = token_data.get("expires_in")
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
            except Exception as ex:
                _LOGGER.exception(ex)
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default="CLP",
                    ): TextSelector(TextSelectorConfig()),
                    vol.Required("email"): TextSelector(TextSelectorConfig()),
                    vol.Required("otp"): TextSelector(TextSelectorConfig()),
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

    @staticmethod
    def async_get_options_flow(config_entry):
        return CLPHKOptionsFlowHandler(config_entry)