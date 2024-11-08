from __future__ import annotations

import base64
import datetime
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
    CONF_USERNAME,
    CONF_PASSWORD,
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
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
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
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
HTTP_401_ERROR_RETRY_LIMIT = 3

DOMAIN = CONF_DOMAIN


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None,
) -> None:
    session = aiohttp_client.async_get_clientsession(hass)

    public_key = serialization.load_pem_public_key(CONF_CLP_PUBLIC_KEY.encode())
    ciphertext = public_key.encrypt(
        config.get(CONF_PASSWORD).encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )
    )

    hass.data[DOMAIN] = {
        'username': config.get(CONF_USERNAME),
        'password': base64.b64encode(ciphertext).decode(),
        'session': session,
    }

    async_add_entities(
        [
            CLPSensor(
                sensor_type='main',
                session=session,
                name=config.get(CONF_NAME),
                timeout=config.get(CONF_TIMEOUT),
                retry_delay=config.get(CONF_RETRY_DELAY),
                type=config.get(CONF_TYPE),
                get_acct=config.get(CONF_GET_ACCT),
                get_bill=config.get(CONF_GET_BILL),
                get_estimation=config.get(CONF_GET_ESTIMATION),
                get_bimonthly=config.get(CONF_GET_BIMONTHLY),
                get_daily=config.get(CONF_GET_DAILY),
                get_hourly=config.get(CONF_GET_HOURLY),
                get_hourly_days=config.get(CONF_GET_HOURLY_DAYS),
            ),
        ],
        update_before_add=True,
    )

    if config.get(CONF_RES_ENABLE):
        async_add_entities(
            [
                CLPSensor(
                    sensor_type='renewable_energy',
                    session=session,
                    name=config.get(CONF_RES_NAME),
                    timeout=config.get(CONF_TIMEOUT),
                    retry_delay=config.get(CONF_RETRY_DELAY),
                    type=config.get(CONF_RES_TYPE),
                    get_acct=False,
                    get_bill=config.get(CONF_RES_GET_BILL),
                    get_estimation=False,
                    get_bimonthly=False,
                    get_daily=config.get(CONF_RES_GET_DAILY),
                    get_hourly=config.get(CONF_RES_GET_HOURLY),
                    get_hourly_days=config.get(CONF_RES_GET_HOURLY_DAYS),
                ),
            ],
            update_before_add=True,
        )


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform(hass, {}, async_add_entities)


def get_dates(timezone):
    return {
        "yesterday": datetime.datetime.now(timezone) + datetime.timedelta(days=-1),
        "today": datetime.datetime.now(timezone),
        "tomorrow": datetime.datetime.now(timezone) + datetime.timedelta(days=1),
        "427_days_ago": (datetime.datetime.now(timezone) + relativedelta.relativedelta(days=-427)),
        "last_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=-1)),
        "this_month": datetime.datetime.now(timezone).replace(day=1),
        "next_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=1)),
    }


def handle_errors(func):
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            await self.hass.services.async_call(
                'persistent_notification',
                'create',
                {
                    'title': f'Error in {self._name} sensor',
                    'message': str(e),
                    'notification_id': f'{self._name}_{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}',
                }
            )

            self.error = str(e)
            _LOGGER.error(f"{self._name} ERROR: {e}", exc_info=True)

            async_call_later(self.hass, self._retry_delay, self.async_update)

            return None

    return wrapper


class CLPSensor(SensorEntity):
    _timezone = pytz.timezone('Asia/Hong_Kong')

    def __init__(
            self,
            sensor_type: str,
            session: aiohttp.ClientSession,
            name: str,
            timeout: int,
            retry_delay: int,
            type: str,
            get_acct: bool,
            get_bill: bool,
            get_estimation: bool,
            get_bimonthly: bool,
            get_daily: bool,
            get_hourly: bool,
            get_hourly_days: int,
    ) -> None:
        self._sensor_type = sensor_type

        self._session = session
        self._username = None
        self._account_number = None
        self._access_token = None
        self._refresh_token = None
        self._access_token_expiry_time = None

        self._name = name
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

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL

        self._account = None
        self._bills = None
        self._estimation = None
        self._bimonthly = None
        self._daily = None
        self._hourly = None

        self._state_data_type = None
        self._single_task_last_fetch_time = None
        self._hourly_task_last_fetch_time = None
        self._daily_task_last_fetch_time = None
        self.error = None
        self._401_error_retry = 0


    @property
    def state_class(self) -> SensorStateClass | str | None:
        return SensorStateClass.TOTAL

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def extra_state_attributes(self) -> dict:
        attr = {
            "state_data_type": self._state_data_type,
            "error": None,
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
            params: dict = None
    ):
        if not self._access_token and 'loginByPassword' not in url and 'refresh_token' not in url:
            raise Exception("Problematic authorization. Please check your username and password, or change your IP address.")

        if json:
            _LOGGER.debug(f"REQUEST {method} {headers} {url} {params} {json}")

        async with async_timeout.timeout(self._timeout):
            response = await self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
            )

            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as e:
                if e.status == 401:
                    self._401_error_retry = self._401_error_retry + 1
                    self._session = aiohttp_client.async_get_clientsession(self.hass)
                    self._username = None
                    self._account_number = None
                    self._access_token = None
                    self._refresh_token = None
                    self._access_token_expiry_time = None

                try:
                    response_data = await response.json()
                    _LOGGER.error(f"{response.status} {response.url} : {response_data}")
                except Exception as _:
                    response_text = await response.text()
                    _LOGGER.error(f"{response.status} {response.url} : {response_text}")

                if self._401_error_retry > HTTP_401_ERROR_RETRY_LIMIT:
                    _LOGGER.error('401 error retry limit reached')
                    raise Exception('401 error retry limit reached')

                raise e

            self._401_error_retry = 0

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


    @handle_errors
    async def auth(self):
        if (
            self._username is None
            or self.hass.data[DOMAIN]['username'] != self._username
            or self._access_token is None
        ):
            response = await self.api_request(
                method="POST",
                url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/accountManagement/loginByPassword",
                json={
                    "username": self.hass.data[DOMAIN]['username'],
                    "password": self.hass.data[DOMAIN]['password'],
                },
            )

            if self.hass.data[DOMAIN]['username'].isdigit() and len(self.hass.data[DOMAIN]['username']) == 11:
                self._account_number = self.hass.data[DOMAIN]['username']

            self._username = self.hass.data[DOMAIN]['username']
            self._access_token = response['data']['access_token']
            self._refresh_token = response['data']['refresh_token']
            self._access_token_expiry_time = datetime.datetime.strptime(response['data']['expires_in'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)

        elif self._access_token_expiry_time and datetime.datetime.now(datetime.timezone.utc) > (self._access_token_expiry_time + datetime.timedelta(minutes=-1)).replace(tzinfo=datetime.timezone.utc):
            response = await self.api_request(
                method="POST",
                url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/identity/manage/account/refresh_token",
                json={
                    "refreshToken": self._refresh_token,
                },
            )
            self._access_token = response['data']['access_token']
            self._refresh_token = response['data']['refresh_token']
            self._access_token_expiry_time = datetime.datetime.strptime(response['data']['expires_in'], '%Y-%m-%dT%H:%M:%S.%fZ') if (response['data']['expires_in'] is not None and response['data']['expires_in'] != '') else None


    @handle_errors
    async def main_get_account_detail(self):
        response = await self.api_request(
            method="GET",
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
            headers={
                "Authorization": self._access_token,
            },
        )
        self._account_number = response['data'][0]['caNo']
        self._account = {
            'number': response['data'][0]['caNo'],
            'outstanding': float(response['data'][0]['outstandingAmount']),
            'due_date': datetime.datetime.strptime(response['data'][0]['dueDate'], '%Y%m%d%H%M%S') if (response['data'][0]['dueDate'] is not None and response['data'][0]['dueDate'] != '') else None,
        }
        self._single_task_last_fetch_time = datetime.datetime.now(self._timezone)


    @handle_errors
    async def main_get_bill(self):
        response = await self.api_request(
            method="POST",
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/billing/transaction/historyBilling",
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
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/info",
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
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/history",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "ca": self._account_number,
                "fromDate": dates["427_days_ago"].strftime('%Y%m%d000000'),
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
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/history",
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
                url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/history",
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
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
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
            url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
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
                url="https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
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
        if self._401_error_retry > HTTP_401_ERROR_RETRY_LIMIT:
            return

        await self.auth()

        if not self._access_token:
            return

        if self._sensor_type == 'main':
            if not self._single_task_last_fetch_time:
                if not self._account_number or self._get_acct:
                    await self.main_get_account_detail()

            if not self._daily_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._daily_task_last_fetch_time + DAILY_TASK_INTERVAL:
                if self._get_bill:
                    await self.main_get_bill()

                if self._get_estimation:
                    await self.main_get_estimation()

                if self._get_bimonthly or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    await self.main_get_bimonthly()

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    await self.main_get_daily()

            if not self._hourly_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._hourly_task_last_fetch_time + HOURLY_TASK_INTERVAL:
                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    await self.main_get_hourly()

        elif self._sensor_type == 'renewable_energy':
            if not self._single_task_last_fetch_time:
                if not self._account_number:
                    await self.main_get_account_detail()

            if not self._daily_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._daily_task_last_fetch_time + DAILY_TASK_INTERVAL:
                if self._get_bill or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    await self.renewable_get_bimonthly()

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    await self.renewable_get_daily()

            if not self._hourly_task_last_fetch_time or datetime.datetime.now(self._timezone) > self._hourly_task_last_fetch_time + HOURLY_TASK_INTERVAL:
                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    await self.renewable_get_hourly()

        if self._type == '' and self._state_data_type is not None:
            self._type = self._state_data_type
