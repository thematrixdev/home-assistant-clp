from __future__ import annotations

import asyncio
import base64
import datetime
import json as jsonlib
import logging

import aiohttp
import async_timeout
import homeassistant.helpers.config_validation as cv
import pytz
import voluptuous as vol
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dateutil import relativedelta
from homeassistant.components.lock import PLATFORM_SCHEMA
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_TIMEOUT,
    CONF_TYPE,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

from . import verify_otp
from .const import (
    CONF_CLP_PUBLIC_KEY,
    CONF_DOMAIN,
    CONF_RETRY_DELAY,

    CONF_GET_ACCT,
    CONF_GET_BILL,
    CONF_GET_ESTIMATION,
    CONF_GET_BIMONTHLY,
    CONF_GET_DAILY,
    CONF_GET_HOURLY,
    CONF_GET_HOURLY_DAYS,

    CONF_RES_ENABLE,
    CONF_RES_NAME,
    CONF_RES_TYPE,
    CONF_RES_GET_BILL,
    CONF_RES_GET_DAILY,
    CONF_RES_GET_HOURLY,
    CONF_RES_GET_HOURLY_DAYS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_TIMEOUT, default=30): cv.positive_int,
    vol.Optional(CONF_RETRY_DELAY, default=300): cv.positive_int,
    vol.Optional(CONF_NAME, default='CLP'): cv.string,
    vol.Optional(CONF_TYPE, default=''): cv.string,
    vol.Optional(CONF_GET_ACCT, default=False): cv.boolean,
    vol.Optional(CONF_GET_BILL, default=False): cv.boolean,
    vol.Optional(CONF_GET_ESTIMATION, default=False): cv.boolean,
    vol.Optional(CONF_GET_BIMONTHLY, default=False): cv.boolean,
    vol.Optional(CONF_GET_DAILY, default=False): cv.boolean,
    vol.Optional(CONF_GET_HOURLY, default=False): cv.boolean,
    vol.Optional(CONF_GET_HOURLY_DAYS, default=1): vol.Clamp(min=1, max=2),

    vol.Optional(CONF_RES_ENABLE, default=False): cv.boolean,
    vol.Optional(CONF_RES_NAME, default='CLP Renewable Energy'): cv.string,
    vol.Optional(CONF_RES_TYPE, default=''): cv.string,
    vol.Optional(CONF_RES_GET_BILL, default=False): cv.boolean,
    vol.Optional(CONF_RES_GET_DAILY, default=False): cv.boolean,
    vol.Optional(CONF_RES_GET_HOURLY, default=False): cv.boolean,
    vol.Optional(CONF_RES_GET_HOURLY_DAYS, default=1): vol.Clamp(min=1, max=2),
})

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=300)
DAILY_TASK_INTERVAL = datetime.timedelta(hours=12)
HOURLY_TASK_INTERVAL = datetime.timedelta(minutes=30)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
HTTP_4xx_ERROR_RETRY_LIMIT = 3

DOMAIN = CONF_DOMAIN

class FatalAuthError(Exception):
    """Non-recoverable auth error that requires reconfiguration."""


API_DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://www.clp.com.hk/",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    if discovery_info is None:
        return

    session = aiohttp_client.async_get_clientsession(hass)

    # Shared token state in hass.data[DOMAIN]
    hass.data[DOMAIN]["session"] = session
    # Set tokens on restart (if not already set)
    for k in ("access_token", "refresh_token", "access_token_expiry_time"):
        if discovery_info.get(k) is not None and discovery_info.get(k) != "":
            hass.data[DOMAIN][k] = discovery_info.get(k)
    hass.data[DOMAIN]["token_lock"] = asyncio.Lock()

    async_add_entities(
        [
            CLPSensor(
                hass=hass,
                sensor_type='main',
                name=discovery_info.get(CONF_NAME, "CLP"),
                email=discovery_info.get("email_address", discovery_info.get("email", None)),
                timeout=int(discovery_info.get(CONF_TIMEOUT, 30)),
                retry_delay=int(discovery_info.get(CONF_RETRY_DELAY, 300)),
                type=discovery_info.get(CONF_TYPE, ""),
                get_acct=discovery_info.get(CONF_GET_ACCT, False),
                get_bill=discovery_info.get(CONF_GET_BILL, False),
                get_estimation=discovery_info.get(CONF_GET_ESTIMATION, False),
                get_bimonthly=discovery_info.get(CONF_GET_BIMONTHLY, False),
                get_daily=discovery_info.get(CONF_GET_DAILY, False),
                get_hourly=discovery_info.get(CONF_GET_HOURLY, False),
                get_hourly_days=int(discovery_info.get(CONF_GET_HOURLY_DAYS, 1)),
            ),
        ],
        update_before_add=True,
    )

    if discovery_info.get(CONF_RES_ENABLE, False):
        async_add_entities(
            [
                CLPSensor(
                    hass=hass,
                    sensor_type='renewable_energy',
                    name=discovery_info.get(CONF_RES_NAME, "CLP Renewable Energy"),
                    email=discovery_info.get("email_address", discovery_info.get("email", None)),
                    timeout=int(discovery_info.get(CONF_TIMEOUT, 30)),
                    retry_delay=int(discovery_info.get(CONF_RETRY_DELAY, 300)),
                    type=discovery_info.get(CONF_RES_TYPE, ""),
                    get_acct=False,
                    get_bill=discovery_info.get(CONF_RES_GET_BILL, False),
                    get_estimation=False,
                    get_bimonthly=False,
                    get_daily=discovery_info.get(CONF_RES_GET_DAILY, False),
                    get_hourly=discovery_info.get(CONF_RES_GET_HOURLY, False),
                    get_hourly_days=int(discovery_info.get(CONF_RES_GET_HOURLY_DAYS, 1)),
                ),
            ],
            update_before_add=True,
        )


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    # Merge config_entry.data and config_entry.options, options take precedence
    merged = {**config_entry.data, **config_entry.options}
    await async_setup_platform(
        hass,
        {},
        async_add_entities,
        discovery_info=merged,
    )


def get_dates(timezone):
    return {
        "yesterday": datetime.datetime.now(timezone) + datetime.timedelta(days=-1),
        "today": datetime.datetime.now(timezone),
        "tomorrow": datetime.datetime.now(timezone) + datetime.timedelta(days=1),
        "one_year_two_months_ago": (datetime.datetime.now(timezone) - relativedelta.relativedelta(years=1, months=2)).replace(day=datetime.datetime.now(timezone).day),
        "last_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=-1)),
        "this_month": datetime.datetime.now(timezone).replace(day=1),
        "next_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=1)),
    }


class ExponentialBackoff:
    def __init__(self, min_delay: int, max_delay: int, factor: float = 2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.factor = factor
        self.delay = min_delay
        self.tries = 0

    def reset(self):
        self.delay = self.min_delay
        self.tries = 0

    def increment(self):
        self.tries += 1
        self.delay = min(self.max_delay, self.delay * self.factor)
        return self.delay


def handle_errors(func):
    async def wrapper(self, *args, **kwargs):
        try:
            # Reset backoff and error state on successful call
            if not hasattr(self, '_backoff'):
                self._backoff = ExponentialBackoff(
                    min_delay=self._retry_delay,
                    max_delay=3600  # Max 1 hour between retries
                )
            
            result = await func(self, *args, **kwargs)
            self._backoff.reset()
            self._error = None
            return result
            
        except Exception as e:
            error_msg = str(e)
            self._error = error_msg
            _LOGGER.error(f"{self._name} ERROR: {error_msg}", exc_info=True)

            if isinstance(e, FatalAuthError):
                _LOGGER.error("%s: Fatal auth error. Integration has been stopped.", self._name)
                return None
            
            # Schedule next retry with exponential backoff
            next_retry_delay = self._backoff.increment()
            _LOGGER.info(f"{self._name}: Scheduling retry in {next_retry_delay} seconds")
            async_call_later(self.hass, next_retry_delay, self.async_update)
            
            return None

    return wrapper


class CLPSensor(SensorEntity):
    _timezone = pytz.timezone('Asia/Hong_Kong')

    def __init__(
            self,
            hass,
            sensor_type: str,
            name: str,
            email: str,
            timeout: int,
            retry_delay: int,
            type: str = None,
            get_acct: bool = False,
            get_bill: bool = False,
            get_estimation: bool = False,
            get_bimonthly: bool = False,
            get_daily: bool = False,
            get_hourly: bool = False,
            get_hourly_days: int = 1,
    ) -> None:
        _LOGGER.debug(f"[SENSOR INIT] type={sensor_type}, name={name}, email={email}, tokens={{'access_token': {getattr(self, '_access_token', None)}, 'expiry': {getattr(self, '_access_token_expiry_time', None)}}}")
        self.hass = hass
        self._sensor_type = sensor_type
        self._name = name
        self._email = email
        self._timeout = timeout
        self._retry_delay = retry_delay
        self._type = type
        self._get_acct = get_acct
        self._get_bill = get_bill
        self._get_estimation = get_estimation
        self._get_bimonthly = get_bimonthly
        self._get_daily = get_daily
        self._get_hourly = get_hourly
        self._get_hourly_days = get_hourly_days
        self._account_number = None
        self._state_data_type = None
        self._error = None
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_name = name
        self._attr_unique_id = f"clphk_{sensor_type}_{name.replace(' ', '_').lower()}"

        self._account = None
        self._bills = None
        self._estimation = None
        self._bimonthly = None
        self._daily = None
        self._hourly = None

        self._single_task_last_fetch_time = None
        self._hourly_task_last_fetch_time = None
        self._daily_task_last_fetch_time = None
        self._4xx_error_retry = 0

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return self._attr_name

    @property
    def state(self):
        return self._attr_native_value

    @property
    def _token_state(self):
        return self.hass.data[DOMAIN]

    @property
    def _access_token(self):
        return self._token_state.get("access_token")

    @property
    def _refresh_token(self):
        return self._token_state.get("refresh_token")

    @property
    def _access_token_expiry_time(self):
        return self._token_state.get("access_token_expiry_time")

    @_access_token.setter
    def _access_token(self, value):
        self._token_state["access_token"] = value

    @_refresh_token.setter
    def _refresh_token(self, value):
        self._token_state["refresh_token"] = value

    @_access_token_expiry_time.setter
    def _access_token_expiry_time(self, value):
        self._token_state["access_token_expiry_time"] = value

    @property
    def _session(self):
        return self._token_state["session"]

    @property
    def extra_state_attributes(self) -> dict:
        attr = {
            "state_data_type": self._state_data_type,
            "error": self._error,
        }

        if self._get_acct and hasattr(self, '_account'):
            attr["account"] = self._account

        if self._get_bill and hasattr(self, '_bills'):
            attr["bills"] = self._bills

        if self._get_estimation and hasattr(self, '_estimation'):
            attr["estimation"] = self._estimation

        if self._get_bimonthly and hasattr(self, '_bimonthly'):
            attr["bimonthly"] = self._bimonthly

        if self._get_daily and hasattr(self, '_daily'):
            attr["daily"] = self._daily

        if self._get_hourly and hasattr(self, '_hourly'):
            attr["hourly"] = self._hourly

        return attr


    async def api_request(
            self,
            method: str,
            url: str,
            headers: dict = None,
            json: dict = None,
            params: dict = None,
            retry_on_expired: bool = True,
    ):
        if not self._access_token and 'eligibilityCheckAndLogin' not in url and 'refresh_token' not in url:
            raise Exception("Problematic authorization. Please configure again, or change your IP address.")

        if json:
            _LOGGER.debug(f"REQUEST {method} {headers} {url} {params} {json}")

        merged_headers = dict(API_DEFAULT_HEADERS)
        if json is not None:
            merged_headers["Content-Type"] = "application/json"
        if headers:
            merged_headers.update(headers)

        async with async_timeout.timeout(self._timeout):
            response = await self._session.request(
                method,
                url,
                headers=merged_headers,
                params=params,
                json=json,
            )

            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as e:
                error_message = f"{e.status} {e.request_info.url}"
                error_data = None
                
                try:
                    # Try to read the response content only once and store it
                    error_content = await response.text()
                    try:
                        error_data = jsonlib.loads(error_content)
                        error_message += f" : {error_data}"
                    except jsonlib.JSONDecodeError:
                        error_message += f" : {error_content}"
                except Exception as read_error:
                    error_message += f" (Failed to read error response: {read_error})"
                
                _LOGGER.error(error_message)

                if 400 <= e.status < 500:
                    # Align with webpage behavior: refresh only after token-expired response.
                    if (
                        retry_on_expired
                        and "refresh_token" not in url
                        and isinstance(error_data, dict)
                        and error_data.get("code") == 906
                        and self._refresh_token
                    ):
                        _LOGGER.debug("Access token expired (906). Refreshing and retrying once.")
                        await self._refresh_access_token()
                        retry_headers = dict(headers or {})
                        if "Authorization" in retry_headers:
                            retry_headers["Authorization"] = self._access_token
                        return await self.api_request(
                            method=method,
                            url=url,
                            headers=retry_headers,
                            json=json,
                            params=params,
                            retry_on_expired=False,
                        )

                    self._account_number = None
                    self._access_token = None
                    self._refresh_token = None
                    self._access_token_expiry_time = None

                    _LOGGER.debug(f"[SENSOR UPDATE] Clearing tokens from config entry.")
                    config_entries = self.hass.config_entries.async_entries(DOMAIN)
                    if config_entries:
                        entry = config_entries[0]
                        data = dict(entry.data)
                        data["access_token"] = ""
                        data["refresh_token"] = ""
                        data["access_token_expiry_time"] = ""
                        self.hass.config_entries.async_update_entry(entry, data=data)

                    raise Exception('HTTP 4xx error retry limit reached')
                    
                raise e

            try:
                response_data = await response.json()

                if not response_data or 'data' not in response_data:
                    _LOGGER.error(f"RESPONSE {response.status} {response.url} : {response_data}")
                    raise ValueError('Invalid response data')

                _LOGGER.debug(f"RESPONSE {response.status} {response.url} : {response_data}")

                return response_data
            except Exception as _:
                response_text = await response.text()
                _LOGGER.error(f"{response.status} {response.url} : {response_text}")
                raise

    async def _refresh_access_token(self):
        """Refresh access token using stored refresh token and persist it."""
        if not self._refresh_token:
            raise Exception("No refresh token available")

        refresh_headers = dict(API_DEFAULT_HEADERS)
        refresh_headers["Content-Type"] = "application/json"

        async with async_timeout.timeout(self._timeout):
            response = await self._session.request(
                "POST",
                "https://api.clp.com.hk/ts1/ms/profile/identity/manage/account/refresh_token",
                headers=refresh_headers,
                json={"refreshToken": self._refresh_token},
            )
            response_text = await response.text()

        if 400 <= response.status < 500:
            await self._handle_refresh_auth_failure(response.status, response_text)
            raise FatalAuthError(
                "Refresh token invalid/expired. CLPHK integration stopped; please reconfigure tokens."
            )
        if response.status >= 500:
            raise Exception(
                f"Refresh token request failed with {response.status}: {response_text[:200]}"
            )

        try:
            response_json = jsonlib.loads(response_text)
        except jsonlib.JSONDecodeError as ex:
            raise Exception(f"Refresh token response is not JSON: {response_text[:200]}") from ex
        if not isinstance(response_json, dict) or "data" not in response_json:
            raise Exception(f"Invalid refresh token response: {response_text[:200]}")
        response_data = response_json["data"]

        self._access_token = response_data['access_token']
        self._refresh_token = response_data['refresh_token']
        self._access_token_expiry_time = response_data['expires_in']

        _LOGGER.debug(f"[SENSOR UPDATE] Persisting refreshed tokens to config entry.")
        config_entries = self.hass.config_entries.async_entries(DOMAIN)
        if config_entries:
            entry = config_entries[0]
            data = dict(entry.data)
            data["access_token"] = self._access_token
            data["refresh_token"] = self._refresh_token
            data["access_token_expiry_time"] = self._access_token_expiry_time
            self.hass.config_entries.async_update_entry(entry, data=data)

    async def _handle_refresh_auth_failure(self, status: int, body: str):
        """Clear tokens, notify frontend, and stop integration on refresh 4xx."""
        self._account_number = None
        self._access_token = None
        self._refresh_token = None
        self._access_token_expiry_time = None

        config_entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in config_entries:
            data = dict(entry.data)
            data["access_token"] = ""
            data["refresh_token"] = ""
            data["access_token_expiry_time"] = ""
            self.hass.config_entries.async_update_entry(entry, data=data)

        message = (
            "CLPHK token refresh failed with HTTP "
            f"{status}. Tokens were cleared and the integration was stopped. "
            "Please reconfigure Access Token and Refresh Token.\n\n"
            f"Response: {body[:300]}"
        )
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "CLPHK Authentication Failed",
                    "message": message,
                    "notification_id": "clphk_auth_failed",
                },
                blocking=False,
            )
        except Exception:
            _LOGGER.warning("Failed to create persistent notification for CLPHK auth failure.")

        for entry in config_entries:
            self.hass.async_create_task(self.hass.config_entries.async_unload(entry.entry_id))


    @handle_errors
    async def auth(self):
        token_lock = self._token_state["token_lock"]
        async with token_lock:
            if not self._access_token and self.hass.states.get('sensor.clp_email_otp') is not None:
                _LOGGER.debug("Requesting OTP")

                state = self.hass.states.get('sensor.clp_email_otp')
                original_otp = state.state if state else None

                public_key = serialization.load_pem_public_key(CONF_CLP_PUBLIC_KEY.encode())
                await self.api_request(
                    method="POST",
                    url="https://api.clp.com.hk/ts1/ms/profile/register/eligibilityCheckAndLogin",
                    json={
                        "email": base64.b64encode(public_key.encrypt(
                            self._email.encode('utf-8'),
                            padding.OAEP(
                                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                                algorithm=hashes.SHA256(),
                                label=None,
                            )
                        )).decode(),
                        "phone": "",
                        "type": base64.b64encode(public_key.encrypt(
                            "email".encode('utf-8'),
                            padding.OAEP(
                                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                                algorithm=hashes.SHA256(),
                                label=None,
                            )
                        )).decode(),
                    },
                )

                await asyncio.sleep(10)

                max_attempts = 15
                attempt = 0
                otp = None
                while attempt < max_attempts:
                    state = self.hass.states.get('sensor.clp_email_otp')
                    otp = state.state if state else None

                    if otp and otp != original_otp:
                        break

                    _LOGGER.debug(f"Waiting for OTP email (attempt {attempt+1}/{max_attempts})...")
                    await asyncio.sleep(5)
                    attempt += 1
                if not otp:
                    _LOGGER.error("OTP was not received in time. Please check your email/IMAP integration.")
                    raise Exception("OTP not received from sensor.clp_email_otp")

                try:
                    token_data = await verify_otp(self._session, self._email, otp)
                    self._access_token = token_data.get("access_token")
                    self._refresh_token = token_data.get("refresh_token")
                    self._access_token_expiry_time = token_data.get("expires_in")
                    _LOGGER.debug(f"Access token obtained: {self._access_token}")
                except Exception as ex:
                    _LOGGER.error(f"Failed to verify OTP and obtain access token: {ex}")
                    raise


    @handle_errors
    async def main_get_account_detail(self):
        response = await self.api_request(
            method="GET",
            url="https://api.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
            headers={
                "Authorization": self._access_token,
            },
        )
        # Find the first entry with status 'Active'
        active_data = next((item for item in response['data'] if item.get('status') == 'Active'), None)
        if not active_data:
            self._account_number = None
            self._account = None
        else:
            self._account_number = active_data['caNo']
            self._account = {
                'number': active_data['caNo'],
                'outstanding': float(active_data['outstandingAmount']),
                'due_date': datetime.datetime.strptime(active_data['dueDate'], '%Y%m%d%H%M%S') if (active_data['dueDate'] is not None and active_data['dueDate'] != '') else None,
            }
        self._single_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_bill(self):
        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/billing/transaction/historyBilling",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "caList": [
                    {
                        "ca": self._account_number,
                    },
                ],
            },
        )

        if response['data']['transactions']:
            bills = {
                'bill': [],
                'payment': [],
            }
            for row in response['data']['transactions']:
                if row['type'] != 'bill' and row['type'] != 'payment':
                    continue

                record = {
                    'total': float(row['total']),
                    'transaction_date': datetime.datetime.strptime(row['tranDate'], '%Y%m%d%H%M%S'),
                }

                if row['type'] == 'bill':
                    record['from_date'] = datetime.datetime.strptime(row['fromDate'], '%Y%m%d%H%M%S')
                    record['to_date'] = datetime.datetime.strptime(row['toDate'], '%Y%m%d%H%M%S')

                bills[row['type']].append(record)

            bills['bill'] = sorted(bills['bill'], key=lambda x: x['transaction_date'], reverse=True)
            bills['payment'] = sorted(bills['payment'], key=lambda x: x['transaction_date'], reverse=True)
            self._bills = bills
            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_estimation(self):
        response = await self.api_request(
            method="GET",
            url="https://api.clp.com.hk/ts1/ms/consumption/info",
            headers={
                "Authorization": self._access_token,
            },
            params={
                "ca": self._account_number,
            },
        )

        if response['data']:
            self._estimation = {
                "current_consumption": float(response['data']['currentConsumption']),
                "current_cost": float(response['data']['currentCost']),
                "current_end_date": datetime.datetime.strptime(response['data']['currentEndDate'], '%Y%m%d%H%M%S') if (response['data']['currentEndDate'] is not None and response['data']['currentEndDate'] != '') else None,
                "current_start_date": datetime.datetime.strptime(response['data']['currentStartDate'], '%Y%m%d%H%M%S') if (response['data']['currentStartDate'] is not None and response['data']['currentStartDate'] != '') else None,
                "deviation_percent": float(response['data']['deviationPercent']),
                "estimation_consumption": float(response['data']['projectedConsumption']),
                "estimation_cost": float(response['data']['projectedCost']),
                "estimation_end_date": datetime.datetime.strptime(response['data']['projectedEndDate'], '%Y%m%d%H%M%S') if (response['data']['projectedEndDate'] is not None and response['data']['projectedEndDate'] != '') else None,
                "estimation_start_date": datetime.datetime.strptime(response['data']['projectedStartDate'], '%Y%m%d%H%M%S') if (response['data']['projectedStartDate'] is not None and response['data']['projectedStartDate'] != '') else None,
            }
            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_bimonthly(self):
        dates = get_dates(self._timezone)

        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/consumption/history",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "ca": self._account_number,
                "fromDate": dates["one_year_two_months_ago"].strftime('%Y%m%d000000'),
                "mode": "Bill",
                "toDate": dates["today"].strftime('%Y%m%d000000'),
                "type": "Unit",
            },
        )

        if response['data']:
            if self._type == '' or self._type.upper() == 'BIMONTHLY':
                self._state_data_type = 'BIMONTHLY'
                self._attr_native_value = response['data']['results'][0]['totKwh']
                self._attr_last_reset = datetime.datetime.strptime(response['data']['results'][0]['endabrpe'], '%Y%m%d')

            if self._get_bimonthly:
                bimonthly = []
                for row in response['data']['results']:
                    bimonthly.append({
                        'end': datetime.datetime.strptime(row['endabrpe'], '%Y%m%d'),
                        'kwh': row['totKwh'],
                    })
                self._bimonthly = sorted(bimonthly, key=lambda x: x['end'], reverse=True)
            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_daily(self):
        dates = get_dates(self._timezone)

        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/consumption/history",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "ca": self._account_number,
                "fromDate": dates["this_month"].strftime("%Y%m%d000000"),
                "mode": "Daily",
                "toDate": dates["next_month"].strftime("%Y%m%d000000"),
                "type": "Unit",
            },
        )

        if response['data']:
            if self._type == '' or self._type.upper() == 'DAILY':
                self._state_data_type = 'DAILY'
                self._attr_native_value = response['data']['results'][-1]['kwhTotal']
                self._attr_last_reset = datetime.datetime.strptime(
                    response['data']['results'][-1]['expireDate'], '%Y%m%d%H%M%S')

            if self._get_daily:
                daily = []
                for row in response['data']['results']:
                    start = None
                    if row['startDate']:
                        start = datetime.datetime.strptime(row['startDate'], '%Y%m%d%H%M%S')

                    end = None
                    if row['expireDate']:
                        end = datetime.datetime.strptime(row['expireDate'], '%Y%m%d%H%M%S')

                    daily.append({
                        'start': start,
                        'end': end,
                        'kwh': row['kwhTotal'],
                    })
                self._daily = sorted(daily, key=lambda x: x['start'], reverse=True)

            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_hourly(self):
        hourly = []
        for i in range(1, self._get_hourly_days + 1):
            from_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(self._get_hourly_days - i))
            to_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(self._get_hourly_days - i - 1))

            if datetime.time(0, 0) <= datetime.datetime.now(self._timezone).time() < datetime.time(4, 0):
                from_date = from_date + datetime.timedelta(days=-1)
                to_date = to_date + datetime.timedelta(days=-1)

            response = await self.api_request(
                method="POST",
                url="https://api.clp.com.hk/ts1/ms/consumption/history",
                headers={
                    "Authorization": self._access_token,
                },
                json={
                    "ca": self._account_number,
                    "fromDate": from_date.strftime("%Y%m%d000000"),
                    "mode": "Hourly",
                    "toDate": to_date.strftime("%Y%m%d000000"),
                    "type": "Unit",
                },
            )

            if response['data']['results']:
                if i == self._get_hourly_days and (self._type == '' or self._type.upper() == 'HOURLY'):
                    self._state_data_type = 'HOURLY'
                    self._attr_native_value = response['data']['results'][-1]['kwhTotal']
                    self._attr_last_reset = datetime.datetime.strptime(
                        response['data']['results'][-1]['expireDate'], '%Y%m%d%H%M%S')

                if self._get_hourly:
                    for row in response['data']['results']:
                        hourly.append({
                            'start': datetime.datetime.strptime(row['startDate'], '%Y%m%d%H%M%S'),
                            'kwh': row['kwhTotal'],
                        })

                self._hourly_task_last_fetch_time = datetime.datetime.now(self._timezone)

        if self._get_hourly:
            self._hourly = sorted(hourly, key=lambda x: x['start'], reverse=True)


    @handle_errors
    async def renewable_get_bimonthly(self):
        dates = get_dates(self._timezone)

        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/renew/fit/dashboard",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "caNo": self._account_number,
                "mode": "B",
                "startDate": dates["today"].strftime("%m/%d/%Y"),
            },
        )

        if response['data']['consumptionData']:
            if self._type == '' or self._type.upper() == 'BIMONTHLY':
                self._state_data_type = 'BIMONTHLY'
                self._attr_native_value = float(response['data']['consumptionData'][-1]['kwhtotal'])
                self._attr_last_reset = datetime.datetime.strptime(response['data']['consumptionData'][-1]['enddate'], '%Y%m%d%H%M%S')

            if self._get_bill:
                bills = []
                for row in response['data']['consumptionData']:
                    bills.append({
                        'start': datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S'),
                        'end': datetime.datetime.strptime(row['enddate'], '%Y%m%d%H%M%S'),
                        'kwh': float(row['kwhtotal']),
                    })
                self._bills = sorted(bills, key=lambda x: x['start'], reverse=True)

            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def renewable_get_daily(self):
        dates = get_dates(self._timezone)

        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/renew/fit/dashboard",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "caNo": self._account_number,
                "mode": "D",
                "startDate": dates["today"].strftime("%m/%d/%Y"),
            },
        )

        if response['data']['consumptionData']:
            if self._type == '' or self._type.upper() == 'DAILY':
                for row in sorted(response['data']['consumptionData'], key=lambda x: x['startdate'], reverse=True):
                    if row['validateStatus'] == 'Y':
                        self._state_data_type = 'DAILY'
                        self._attr_native_value = float(row['kwhtotal'])
                        self._attr_last_reset = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')
                        break

            if self._get_daily:
                daily = []

                for row in response['data']['consumptionData']:
                    start = None
                    if row['startdate']:
                        start = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')

                    daily.append({
                        'start': start,
                        'kwh': float(row['kwhtotal']),
                    })

                self._daily = sorted(daily, key=lambda x: x['start'], reverse=True)

            self._daily_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def renewable_get_hourly(self):
        hourly = []
        for i in range(1, self._get_hourly_days + 1):
            start_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(self._get_hourly_days - i))

            if datetime.time(0, 0) <= datetime.datetime.now(self._timezone).time() < datetime.time(4, 0):
                start_date = start_date + datetime.timedelta(days=-1)

            response = await self.api_request(
                method="POST",
                url="https://api.clp.com.hk/ts1/ms/renew/fit/dashboard",
                headers={
                    "Authorization": self._access_token,
                },
                json={
                    "caNo": self._account_number,
                    "mode": "H",
                    "startDate": start_date.strftime("%m/%d/%Y"),
                },
            )

            if response['data']['consumptionData']:
                if i == 1 and (self._type == '' or self._type.upper() == 'HOURLY'):
                    for row in sorted(response['data']['consumptionData'], key=lambda x: x['startdate'], reverse=True):
                        if row['validateStatus'] == 'Y':
                            self._state_data_type = 'HOURLY'
                            self._attr_native_value = float(row['kwhtotal'])
                            self._attr_last_reset = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')
                            break

                if self._get_hourly:
                    for row in response['data']['consumptionData']:
                        if row['validateStatus'] == 'N':
                            continue

                        hourly.append({
                            'start': datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S'),
                            'kwh': float(row['kwhtotal']),
                        })

                self._hourly_task_last_fetch_time = datetime.datetime.now(self._timezone)

        if self._get_hourly:
            self._hourly = sorted(hourly, key=lambda x: x['start'], reverse=True)


    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        _LOGGER.debug(f"[SENSOR UPDATE] Starting update for {self._sensor_type}, access_token_expiry_time={self._access_token_expiry_time}")

        if self._4xx_error_retry > HTTP_4xx_ERROR_RETRY_LIMIT:
            _LOGGER.debug(f"[SENSOR UPDATE] 4xx error retry limit reached, skipping update.")
            return

        await self.auth()

        if not self._access_token:
            _LOGGER.debug(f"[SENSOR UPDATE] No access token, skipping data fetch.")
            return

        if self._sensor_type == 'main':
            if not self._single_task_last_fetch_time:
                if not self._account_number or self._get_acct:
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching account detail.")
                    await self.main_get_account_detail()

            if not self._daily_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._daily_task_last_fetch_time + DAILY_TASK_INTERVAL:
                if self._get_bill:
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching bill.")
                    await self.main_get_bill()

                if self._get_estimation:
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching estimation.")
                    await self.main_get_estimation()

                if self._get_bimonthly or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching bimonthly.")
                    await self.main_get_bimonthly()

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching daily.")
                    await self.main_get_daily()

            if not self._hourly_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._hourly_task_last_fetch_time + HOURLY_TASK_INTERVAL:
                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching hourly.")
                    await self.main_get_hourly()

        elif self._sensor_type == 'renewable_energy':
            if not self._single_task_last_fetch_time:
                if not self._account_number:
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching renewable account detail.")
                    await self.main_get_account_detail()

            if not self._daily_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._daily_task_last_fetch_time + DAILY_TASK_INTERVAL:
                if self._get_bill or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching renewable bimonthly.")
                    await self.renewable_get_bimonthly()

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching renewable daily.")
                    await self.renewable_get_daily()

            if not self._hourly_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._hourly_task_last_fetch_time + HOURLY_TASK_INTERVAL:
                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug(f"[SENSOR UPDATE] Fetching renewable hourly.")
                    await self.renewable_get_hourly()

        if self._type == '' and self._state_data_type is not None:
            self._type = self._state_data_type
