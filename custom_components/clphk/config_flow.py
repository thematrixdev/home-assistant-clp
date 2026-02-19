"""Config flow for CLP integration."""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_NAME,
    CONF_TIMEOUT,
    CONF_TYPE,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
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
    CONF_RETRY_DELAY,
)

_LOGGER = logging.getLogger(__name__)

CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

API_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://www.clp.com.hk/",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME,
                default=defaults.get(CONF_NAME, "CLP"),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_TIMEOUT,
                default=defaults.get(CONF_TIMEOUT, 30),
            ): NumberSelector(NumberSelectorConfig(min=1, max=120, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_RETRY_DELAY,
                default=defaults.get(CONF_RETRY_DELAY, 300),
            ): NumberSelector(NumberSelectorConfig(min=60, max=3600, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_TYPE,
                default=defaults.get(CONF_TYPE, ""),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_GET_ACCT,
                default=defaults.get(CONF_GET_ACCT, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_BILL,
                default=defaults.get(CONF_GET_BILL, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_ESTIMATION,
                default=defaults.get(CONF_GET_ESTIMATION, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_BIMONTHLY,
                default=defaults.get(CONF_GET_BIMONTHLY, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_DAILY,
                default=defaults.get(CONF_GET_DAILY, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_HOURLY,
                default=defaults.get(CONF_GET_HOURLY, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_GET_HOURLY_DAYS,
                default=defaults.get(CONF_GET_HOURLY_DAYS, 1),
            ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_RES_ENABLE,
                default=defaults.get(CONF_RES_ENABLE, False),
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
                default=defaults.get(CONF_RES_GET_BILL, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_DAILY,
                default=defaults.get(CONF_RES_GET_DAILY, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_HOURLY,
                default=defaults.get(CONF_RES_GET_HOURLY, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_RES_GET_HOURLY_DAYS,
                default=defaults.get(CONF_RES_GET_HOURLY_DAYS, 1),
            ): NumberSelector(NumberSelectorConfig(min=1, max=2, mode=NumberSelectorMode.BOX)),
        }
    )


def _try_b64_decode(value: str) -> str | None:
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except Exception:
        return None
    if not decoded or any(ord(ch) < 32 for ch in decoded):
        return None
    return decoded


def _extract_allowed_b64_token(raw_value: str) -> str | None:
    """Accept only: JSON object with data, JSON string, or plain base64 string."""
    value = (raw_value or "").strip()
    if not value:
        return None

    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            token = parsed.get("data")
            if not isinstance(token, str):
                return None
            candidate = token.strip()
        elif isinstance(parsed, str):
            candidate = parsed.strip()
        else:
            return None
    except Exception:
        candidate = value

    # Explicitly reject unsupported formats.
    if candidate.startswith("Bearer "):
        return None

    decoded = _try_b64_decode(candidate)
    if not decoded or not UUID_RE.match(decoded):
        return None
    return candidate


def _normalize_token(raw_value: str) -> tuple[str | None, str]:
    """Return decoded UUID token from accepted input format."""
    b64_token = _extract_allowed_b64_token(raw_value)
    if not b64_token:
        return None, "token_format_invalid"

    decoded = _try_b64_decode(b64_token)
    if not decoded or not UUID_RE.match(decoded):
        return None, "token_format_invalid"
    return decoded, ""


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


async def _validate_access_token(session, token: str, timeout: int = 30) -> tuple[str | None, str]:
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
        async with async_timeout.timeout(timeout):
            async with session.get(
                "https://api.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
                headers=headers,
            ) as response:
                body = await response.text()
                if response.status != 200:
                    last_error = _classify_access_token_error(response.status, body)
                    return None, last_error
                data = json.loads(body)
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    return normalized, ""
    except Exception:
        last_error = "cannot_connect"
    return None, last_error


class CLPHKOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow: tokens -> options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._merged_data = {**config_entry.data, **config_entry.options}
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input=None) -> FlowResult:
        return await self.async_step_tokens(user_input)

    async def async_step_tokens(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            access_token_input = user_input[CONF_ACCESS_TOKEN]
            refresh_token_input = user_input[CONF_REFRESH_TOKEN]
            session = aiohttp_client.async_get_clientsession(self.hass)
            timeout = int(self._merged_data.get(CONF_TIMEOUT, 30))
            normalized_access_token, error_key = await _validate_access_token(
                session=session,
                token=access_token_input,
                timeout=timeout,
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

        defaults = self._merged_data
        return self.async_show_form(
            step_id="tokens",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")): TextSelector(TextSelectorConfig()),
                    vol.Required(CONF_REFRESH_TOKEN, default=defaults.get(CONF_REFRESH_TOKEN, "")): TextSelector(TextSelectorConfig()),
                }
            ),
            errors=errors,
        )

    async def async_step_options(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_ACCESS_TOKEN: self._pending[CONF_ACCESS_TOKEN],
                    CONF_REFRESH_TOKEN: self._pending[CONF_REFRESH_TOKEN],
                },
                options=user_input,
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title=self.config_entry.title, data=user_input)

        return self.async_show_form(
            step_id="options",
            data_schema=_build_options_schema(self._merged_data),
            errors={},
        )


class ConfigFlow(config_entries.ConfigFlow, domain="clphk"):
    """Setup flow: tokens -> options."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_tokens(user_input)

    async def async_step_tokens(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            access_token_input = user_input[CONF_ACCESS_TOKEN]
            refresh_token_input = user_input[CONF_REFRESH_TOKEN]
            session = aiohttp_client.async_get_clientsession(self.hass)
            normalized_access_token, error_key = await _validate_access_token(
                session=session,
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): TextSelector(TextSelectorConfig()),
                    vol.Required(CONF_REFRESH_TOKEN): TextSelector(TextSelectorConfig()),
                }
            ),
            errors=errors,
        )

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
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

    @staticmethod
    def async_get_options_flow(config_entry):
        return CLPHKOptionsFlowHandler(config_entry)
