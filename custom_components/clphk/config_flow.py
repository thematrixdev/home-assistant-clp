"""Config flow for CLP integration."""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any
from collections.abc import Mapping

import asyncio

import voluptuous as vol
from curl_cffi.requests import AsyncSession
from homeassistant import config_entries
from homeassistant.const import (
    CONF_NAME,
    CONF_TIMEOUT,
    CONF_TYPE,
)
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_COMBINED_TOKENS,
    CONF_CUSTOM_FIXED_RATE,
    CONF_CUSTOM_FUEL_CENTS,
    CONF_CUSTOM_RATE_ENTITY,
    CONF_CUSTOM_SUBSIDY,
    CONF_GET_ACCT,
    CONF_GET_BILL,
    CONF_GET_BIMONTHLY,
    CONF_GET_DAILY,
    CONF_GET_ESTIMATION,
    CONF_GET_HOURLY,
    CONF_GET_HOURLY_DAYS,
    CONF_RES_ENABLE,
    CONF_RES_GET_BILL,
    CONF_RES_GET_DAILY,
    CONF_RES_GET_HOURLY,
    CONF_RES_GET_HOURLY_DAYS,
    CONF_RES_NAME,
    CONF_RES_TYPE,
    UUID_RE,
    _extract_allowed_b64_token,
    _try_b64_decode,
    parse_combined_tokens,
)

_LOGGER = logging.getLogger(__name__)

CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

# Browser fingerprint headers are set by curl_cffi's impersonate="chrome";
# only app-level headers are declared here (see sensor.py for rationale).
API_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
    "Referer": "https://www.clp.com.hk/",
}


def _build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            # 1. Electricity Tariff & Price Configuration (User Customization)
            vol.Optional(
                CONF_CUSTOM_FIXED_RATE,
                default=float(defaults.get(CONF_CUSTOM_FIXED_RATE, 0.0) or 0.0),
            ): NumberSelector(NumberSelectorConfig(min=0, max=10, step=0.001, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_CUSTOM_FUEL_CENTS,
                default=float(defaults.get(CONF_CUSTOM_FUEL_CENTS, 0.0) or 0.0),
            ): NumberSelector(NumberSelectorConfig(min=0, max=200, step=0.1, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_CUSTOM_SUBSIDY,
                default=float(defaults.get(CONF_CUSTOM_SUBSIDY, 0.0) or 0.0),
            ): NumberSelector(NumberSelectorConfig(min=0, max=2000, step=1, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_CUSTOM_RATE_ENTITY,
                default=defaults.get(CONF_CUSTOM_RATE_ENTITY, ""),
            ): TextSelector(TextSelectorConfig()),

            # 2. Main Sensor Data Collection Items
            vol.Optional(
                CONF_GET_HOURLY,
                default=bool(defaults.get(CONF_GET_HOURLY, True)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_HOURLY_DAYS,
                default=int(defaults.get(CONF_GET_HOURLY_DAYS, 1)),
            ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_GET_DAILY,
                default=bool(defaults.get(CONF_GET_DAILY, True)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_ESTIMATION,
                default=bool(defaults.get(CONF_GET_ESTIMATION, True)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_BILL,
                default=bool(defaults.get(CONF_GET_BILL, True)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_BIMONTHLY,
                default=bool(defaults.get(CONF_GET_BIMONTHLY, False)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_ACCT,
                default=bool(defaults.get(CONF_GET_ACCT, False)),
            ): BooleanSelector(),

            # 3. Basic Preferences
            vol.Required(
                CONF_NAME,
                default=defaults.get(CONF_NAME, "CLP"),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_TIMEOUT,
                default=int(defaults.get(CONF_TIMEOUT, 30)),
            ): NumberSelector(NumberSelectorConfig(min=1, max=120, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_TYPE,
                default=defaults.get(CONF_TYPE, ""),
            ): TextSelector(TextSelectorConfig()),

            # 4. Optional Token Update (leave blank to keep current credentials unchanged)
            vol.Optional(
                CONF_COMBINED_TOKENS,
                default="",
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_ACCESS_TOKEN,
                default="",
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_REFRESH_TOKEN,
                default="",
            ): TextSelector(TextSelectorConfig()),

            # 5. Renewable Energy (Feed-in Tariff FiT)
            vol.Optional(
                CONF_RES_ENABLE,
                default=bool(defaults.get(CONF_RES_ENABLE, False)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_NAME,
                default=defaults.get(CONF_RES_NAME, "CLP Renewable Energy"),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_RES_TYPE,
                default=defaults.get(CONF_RES_TYPE, ""),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_RES_GET_BILL,
                default=bool(defaults.get(CONF_RES_GET_BILL, False)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_DAILY,
                default=bool(defaults.get(CONF_RES_GET_DAILY, False)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_HOURLY,
                default=bool(defaults.get(CONF_RES_GET_HOURLY, False)),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_HOURLY_DAYS,
                default=int(defaults.get(CONF_RES_GET_HOURLY_DAYS, 1)),
            ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
        }
    )



CONF_COMBINED_TOKENS = "combined_tokens"


def _build_tokens_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_COMBINED_TOKENS,
                default="",
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_ACCESS_TOKEN,
                default=defaults.get(CONF_ACCESS_TOKEN, ""),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_REFRESH_TOKEN,
                default=defaults.get(CONF_REFRESH_TOKEN, ""),
            ): TextSelector(TextSelectorConfig()),
        }
    )




def _normalize_token(raw_value: str | None) -> tuple[str | None, str]:
    """Return decoded UUID token from accepted input format (plain UUID, Bearer, JSON, or base64)."""
    token_str = _extract_allowed_b64_token(raw_value)
    if not token_str:
        return None, "token_format_invalid"

    # If it is already a UUID string
    if UUID_RE.match(token_str):
        return token_str.lower(), ""

    # If it is base64-encoded
    decoded = _try_b64_decode(token_str)
    if decoded:
        dec_clean = decoded.strip("\"'").strip()
        if dec_clean.lower().startswith("bearer "):
            dec_clean = dec_clean[7:].strip()
        if UUID_RE.match(dec_clean):
            return dec_clean.lower(), ""

    return None, "token_format_invalid"


def _classify_access_token_error(status: int, body: str) -> str:
    """Map API failure to a clearer config-flow error key."""
    try:
        payload = json.loads(body)
        code = payload.get("code")
        message = str(payload.get("message", "")).lower()
        if code == 906 or "expired" in message:
            return "access_token_expired"
        if code == 100001 or "access_token error" in message:
            return "access_token_invalid"
    except Exception:
        pass

    if status == 403 and "Access Denied" in body:
        return "akamai_blocked"
    if status in (401, 403):
        return "access_token_invalid"
    if status >= 500:
        return "cannot_connect"
    return "invalid_auth"


async def _validate_access_token(token: str, timeout: int = 30) -> tuple[str | None, str]:
    """Return (normalized token, error key)."""
    normalized, format_error = _normalize_token(token)
    if not normalized:
        return None, format_error

    last_error = "invalid_auth"
    headers = {
        **API_DEFAULT_HEADERS,
        "Authorization": normalized,
    }
    try:
        async with asyncio.timeout(timeout):
            async with AsyncSession() as session:
                response = await session.get(
                    "https://api.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
                    headers=headers,
                    impersonate="chrome",
                )
        body = response.text or ""
        status = response.status_code
        if status != 200:
            return None, _classify_access_token_error(status, body)
        data = json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return normalized, ""
    except Exception:
        last_error = "cannot_connect"
    return None, last_error


class CLPHKOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow: direct options form with electricity tariff configuration & optional token update."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        defaults = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            combined = (user_input.get(CONF_COMBINED_TOKENS) or "").strip()
            act_input = (user_input.get(CONF_ACCESS_TOKEN) or "").strip()
            rct_input = (user_input.get(CONF_REFRESH_TOKEN) or "").strip()

            new_access_token = None
            new_refresh_token = None

            if combined:
                act_parsed, rct_parsed = parse_combined_tokens(combined)
                if not act_parsed or not rct_parsed:
                    errors["base"] = "token_format_invalid"
                else:
                    act_input, rct_input = act_parsed, rct_parsed

            if not errors and (act_input or rct_input):
                if not act_input or not rct_input:
                    errors["base"] = "token_format_invalid"
                else:
                    timeout = int(user_input.get(CONF_TIMEOUT, defaults.get(CONF_TIMEOUT, 30)))
                    norm_act, error_key = await _validate_access_token(
                        token=act_input,
                        timeout=timeout,
                    )
                    if not norm_act:
                        errors["base"] = error_key
                    else:
                        norm_rct, refresh_error = _normalize_token(rct_input)
                        if not norm_rct:
                            errors["base"] = refresh_error
                        else:
                            new_access_token = norm_act
                            new_refresh_token = norm_rct

            if not errors:
                clean_options = {
                    k: v
                    for k, v in user_input.items()
                    if k not in (CONF_COMBINED_TOKENS, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN)
                }
                new_data = dict(self.config_entry.data)
                if new_access_token and new_refresh_token:
                    new_data[CONF_ACCESS_TOKEN] = new_access_token
                    new_data[CONF_REFRESH_TOKEN] = new_refresh_token

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                    options=clean_options,
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title=self.config_entry.title, data=clean_options)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(defaults),
            errors=errors,
        )

    async def async_step_options(self, user_input=None) -> ConfigFlowResult:
        return await self.async_step_init(user_input)


class ConfigFlow(config_entries.ConfigFlow, domain="clphk"):
    """Setup flow: user (guide) -> tokens -> options."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_tokens()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

    async def async_step_tokens(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            combined = (user_input.get(CONF_COMBINED_TOKENS) or "").strip()
            if combined:
                access_token_input, refresh_token_input = parse_combined_tokens(combined)
            else:
                access_token_input = user_input.get(CONF_ACCESS_TOKEN)
                refresh_token_input = user_input.get(CONF_REFRESH_TOKEN)
            normalized_access_token, error_key = await _validate_access_token(
                token=access_token_input,
                timeout=30,
            )
            if not normalized_access_token:
                errors["base"] = error_key
            else:
                normalized_refresh_token, refresh_error = _normalize_token(refresh_token_input)
                if not normalized_refresh_token:
                    errors["base"] = refresh_error
                    normalized_access_token = None
                else:
                    self._pending[CONF_ACCESS_TOKEN] = normalized_access_token
                    self._pending[CONF_REFRESH_TOKEN] = normalized_refresh_token
                    return await self.async_step_options()

        return self.async_show_form(
            step_id="tokens",
            data_schema=_build_tokens_schema({}),
            errors=errors,
        )

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {
                **user_input,
                CONF_ACCESS_TOKEN: self._pending[CONF_ACCESS_TOKEN],
                CONF_REFRESH_TOKEN: self._pending[CONF_REFRESH_TOKEN],
            }
            return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="options",
            data_schema=_build_options_schema({}),
            errors={},
        )


    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle reauth flow when tokens expire."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        """Dialog prompting user to paste new tokens."""
        errors: dict[str, str] = {}
        if user_input is not None:
            combined = (user_input.get(CONF_COMBINED_TOKENS) or "").strip()
            if combined:
                access_token_input, refresh_token_input = parse_combined_tokens(combined)
            else:
                access_token_input = user_input.get(CONF_ACCESS_TOKEN)
                refresh_token_input = user_input.get(CONF_REFRESH_TOKEN)

            if not access_token_input or not refresh_token_input:
                errors["base"] = "token_format_invalid"
            else:
                normalized_access_token, error_key = await _validate_access_token(
                    token=access_token_input,
                    timeout=30,
                )
                if not normalized_access_token:
                    errors["base"] = error_key
                else:
                    normalized_refresh_token, refresh_error = _normalize_token(refresh_token_input)
                    if not normalized_refresh_token:
                        errors["base"] = refresh_error
                    else:
                        if self._reauth_entry:
                            self.hass.config_entries.async_update_entry(
                                self._reauth_entry,
                                data={
                                    **self._reauth_entry.data,
                                    CONF_ACCESS_TOKEN: normalized_access_token,
                                    CONF_REFRESH_TOKEN: normalized_refresh_token,
                                },
                            )
                            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                        return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_build_tokens_schema({}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return CLPHKOptionsFlowHandler()
