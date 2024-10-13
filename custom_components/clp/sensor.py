from __future__ import annotations

import base64
import datetime
import logging

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
    CONF_GET_DAILY,
    CONF_GET_HOURLY,

    CONF_RES_ENABLE,
    CONF_RES_NAME,
    CONF_RES_TYPE,
    CONF_RES_GET_BILL,
    CONF_RES_GET_DAILY,
    CONF_RES_GET_HOURLY,
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
    vol.Optional(CONF_GET_DAILY, default=False): cv.boolean,
    vol.Optional(CONF_GET_HOURLY, default=False): cv.boolean,

    vol.Optional(CONF_RES_ENABLE, default=False): cv.boolean,
    vol.Optional(CONF_RES_NAME, default='CLP Renewable Energy'): cv.string,
    vol.Optional(CONF_RES_TYPE, default=''): cv.string,
    vol.Optional(CONF_RES_GET_BILL, default=False): cv.boolean,
    vol.Optional(CONF_RES_GET_DAILY, default=False): cv.boolean,
    vol.Optional(CONF_RES_GET_HOURLY, default=False): cv.boolean,
})

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=60)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

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
                get_daily=config.get(CONF_GET_DAILY),
                get_hourly=config.get(CONF_GET_HOURLY),
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
                    get_daily=config.get(CONF_RES_GET_DAILY),
                    get_hourly=config.get(CONF_RES_GET_HOURLY),
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
        "last_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=-1)),
        "this_month": datetime.datetime.now(timezone).replace(day=1),
        "next_month": (datetime.datetime.now(timezone).replace(day=1) + relativedelta.relativedelta(months=1)),
    }


async def login(session, username, password, timeout):
    async with async_timeout.timeout(timeout):
        response = await session.request(
            "POST",
            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/accountManagement/loginByPassword",
            json={
                "username": username,
                "password": password,
            },
        )
        response.raise_for_status()
        response = await response.json()
        return response['data']['access_token'], response['data']['refresh_token'], response['data']['expires_in']


async def refresh_token(session, refresh_token, timeout):
    async with async_timeout.timeout(timeout):
        response = await session.request(
            "POST",
            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/identity/manage/account/refresh_token",
            json={
                "refreshToken": refresh_token,
            },
        )
        response.raise_for_status()
        response = await response.json()
        return response['data']['access_token'], response['data']['refresh_token'], response['data']['expires_in']


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
            get_daily: bool,
            get_hourly: bool,
    ) -> None:
        self._sensor_type = sensor_type

        self._session = session
        self._username = None
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
        self._get_daily = get_daily
        self._get_hourly = get_hourly

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL

        self._account = None
        self._bills = None
        self._estimation = None
        self._daily = None
        self._hourly = None

        self._state_data_type = None
        self.error = None

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

        if hasattr(self, '_account'):
            attr["account"] = self._account

        if hasattr(self, '_eco_points'):
            attr["eco_points"] = self._eco_points

        if hasattr(self, '_bills'):
            attr["bills"] = self._bills

        if hasattr(self, '_billed'):
            attr["billed"] = self._billed

        if hasattr(self, '_unbilled'):
            attr["unbilled"] = self._unbilled

        if hasattr(self, '_daily'):
            attr["daily"] = self._daily

        if hasattr(self, '_hourly'):
            attr["hourly"] = self._hourly

        return attr

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        try:
            dates = get_dates(self._timezone)

            if (
                self._username is None
                or self.hass.data[DOMAIN]['username'] != self._username
                or self._access_token is None
                or (
                    self._access_token_expiry_time
                    and datetime.datetime.now(datetime.timezone.utc) > datetime.datetime.strptime(self._access_token_expiry_time, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
                )
            ):
                self._access_token, self._refresh_token, self._access_token_expiry_time = await login(
                    session=self._session,
                    username=self.hass.data[DOMAIN]['username'],
                    password=self.hass.data[DOMAIN]['password'],
                    timeout=self._timeout,
                )
                self._username = self.hass.data[DOMAIN]['username']
            else:
                self._access_token, self._refresh_token, self._access_token_expiry_time = await refresh_token(
                    session=self._session,
                    refresh_token=self._refresh_token,
                    timeout=self._timeout,
                )

            if self._sensor_type == 'main':
                if self._get_acct:
                    _LOGGER.debug("CLP ACCOUNT")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "GET",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
                            headers={
                                "Authorization": self._access_token,
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()
                        self._account = {
                            'number': data['data'][0]['caNo'],
                            'outstanding': float(data['data'][0]['outstandingAmount']),
                        }
                        _LOGGER.debug(data)

                if self._get_bill:
                    _LOGGER.debug("CLP BILL")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/billing/transaction/historyBilling",
                            headers={
                                "Authorization": self._access_token,
                            },
                            json={
                                "caList": [
                                    {
                                        "ca": self.hass.data[DOMAIN]['username'],
                                    },
                                ],
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['data']['transactions']:
                            bills = []
                            for row in data['data']['transactions']:
                                bills.append({
                                    'from_date': datetime.datetime.strptime(row['fromDate'], '%Y%m%d%H%M%S') if row['fromDate'] != "" else None,
                                    'to_date': datetime.datetime.strptime(row['toDate'], '%Y%m%d%H%M%S') if row['toDate'] != "" else None,
                                    'total': row['total'],
                                    'transaction_date': datetime.datetime.strptime(row['tranDate'], '%Y%m%d%H%M%S'),
                                    'type': row['type'],

                                })
                            self._bills = bills

                if self._get_estimation:
                    _LOGGER.debug("CLP ESTIMATION")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "GET",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/info?ca=" + self.hass.data[DOMAIN]['username'],
                            headers={
                                "Authorization": self._access_token,
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()
                        self._estimation = data['data']
                        _LOGGER.debug(data)

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug("CLP DAILY")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/history",
                            headers={
                                "Authorization": self._access_token,
                            },
                            json={
                                "ca": self.hass.data[DOMAIN]['username'],
                                "fromDate": dates["this_month"].strftime("%Y%m%d000000"),
                                "mode": "Daily",
                                "toDate": dates["next_month"].strftime("%Y%m%d000000"),
                                "type": "Unit",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['data']:
                            if self._type == '' or self._type.upper() == 'DAILY':
                                self._state_data_type = 'DAILY'
                                self._attr_native_value = data['data']['results'][-1]['kwhTotal']
                                self._attr_last_reset = datetime.datetime.strptime(
                                    data['data']['results'][-1]['expireDate'], '%Y%m%d%H%M%S')

                            if self._get_daily:
                                self._daily = []
                                for row in data['data']['results']:
                                    start = None
                                    if row['startDate']:
                                        start = datetime.datetime.strptime(row['startDate'], '%Y%m%d%H%M%S')

                                    end = None
                                    if row['expireDate']:
                                        end = datetime.datetime.strptime(row['expireDate'], '%Y%m%d%H%M%S')

                                    self._daily.append({
                                        'start': start,
                                        'end': end,
                                        'kwh': row['kwhTotal'],
                                    })

                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug("CLP HOURLY")

                    if self._get_hourly:
                        self._hourly = []

                    async with async_timeout.timeout(self._timeout):
                        for i in range(2):
                            if i == 0:
                                from_date = dates["yesterday"]
                                to_date = dates["today"]
                            else:
                                from_date = dates["today"]
                                to_date = dates["tomorrow"]

                        response = await self._session.request(
                            "POST",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/consumption/history",
                            headers={
                                "Authorization": self._access_token,
                            },
                            json={
                                "ca": self.hass.data[DOMAIN]['username'],
                                "fromDate": from_date.strftime("%Y%m%d000000"),
                                "mode": "Hourly",
                                "toDate": to_date.strftime("%Y%m%d000000"),
                                "type": "Unit",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['data']['results']:
                            if i == 1 and (self._type == '' or self._type.upper() == 'HOURLY'):
                                self._state_data_type = 'HOURLY'
                                self._attr_native_value = data['data']['results'][-1]['kwhTotal']
                                self._attr_last_reset = datetime.datetime.strptime(
                                    data['data']['results'][-1]['expireDate'], '%Y%m%d%H%M%S')

                            if self._get_hourly:
                                for row in data['data']['results']:
                                    self._hourly.append({
                                        'start': datetime.datetime.strptime(row['startDate'], '%Y%m%d%H%M%S'),
                                        'kwh': row['kwhTotal'],
                                    })

            elif self._sensor_type == 'renewable_energy':
                _LOGGER.debug("CLP Renewable-Energy")

                if self._get_bill or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    _LOGGER.debug("CLP BILL")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
                            headers={
                                "Authorization": self._access_token,
                            },
                            json={
                                "caNo": self.hass.data[DOMAIN]['username'],
                                "mode": "B",
                                "startDate": dates["today"].strftime("%m/%d/%Y"),
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['data']['consumptionData']:
                            if self._type == '' or self._type.upper() == 'BIMONTHLY':
                                self._state_data_type = 'BIMONTHLY'
                                self._attr_native_value = float(data['data']['consumptionData'][-1]['kwhtotal'])
                                self._attr_last_reset = datetime.datetime.strptime(data['data']['consumptionData'][-1]['enddate'], '%Y%m%d%H%M%S')

                            if self._get_bill:
                                self._bills = []
                                for row in data['data']['consumptionData']:
                                    self._bills.append({
                                        'start': datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S'),
                                        'end': datetime.datetime.strptime(row['enddate'], '%Y%m%d%H%M%S'),
                                        'kwh': float(row['kwhtotal']),
                                    })

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug("CLP DAILY")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
                            headers={
                                "Authorization": self._access_token,
                            },
                            json={
                                "caNo": self.hass.data[DOMAIN]['username'],
                                "mode": "D",
                                "startDate": dates["today"].strftime("%m/%d/%Y"),
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['data']['consumptionData']:
                            if self._type == '' or self._type.upper() == 'DAILY':
                                for row in sorted(data['data']['consumptionData'], key=lambda x: x['startdate'], reverse=True):
                                    if row['validateStatus'] == 'Y':
                                        self._state_data_type = 'DAILY'
                                        self._attr_native_value = float(row['kwhtotal'])
                                        self._attr_last_reset = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')
                                        break

                            if self._get_daily:
                                self._daily = []

                                for row in data['data']['consumptionData']:
                                    start = None
                                    if row['startdate']:
                                        start = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')

                                    self._daily.append({
                                        'start': start,
                                        'kwh': float(row['kwhtotal']),
                                    })

                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug("CLP HOURLY")

                    if self._get_hourly:
                        self._hourly = []

                    async with async_timeout.timeout(self._timeout):
                        for i in range(2):
                            if i == 0:
                                start = dates["yesterday"].strftime("%m/%d/%Y")
                            else:
                                start = dates["today"].strftime("%m/%d/%Y")

                            response = await self._session.request(
                                "POST",
                                "https://clpapigee.eipprod.clp.com.hk/ts1/ms/renew/fit/dashboard",
                                headers={
                                    "Authorization": self._access_token,
                                },
                                json={
                                    "caNo": self.hass.data[DOMAIN]['username'],
                                    "mode": "H",
                                    "startDate": start,
                                },
                            )
                            response.raise_for_status()
                            data = await response.json()

                            _LOGGER.debug(data)

                            if data['data']['consumptionData']:
                                if i == 1 and (self._type == '' or self._type.upper() == 'HOURLY'):
                                    for row in sorted(data['data']['consumptionData'], key=lambda x: x['startdate'], reverse=True):
                                        if row['validateStatus'] == 'Y':
                                            self._state_data_type = 'HOURLY'
                                            self._attr_native_value = float(row['kwhtotal'])
                                            self._attr_last_reset = datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S')
                                            break

                                if self._get_hourly:
                                    for row in data['data']['consumptionData']:
                                        if row['validateStatus'] == 'N':
                                            continue

                                        self._hourly.append({
                                            'start': datetime.datetime.strptime(row['startdate'], '%Y%m%d%H%M%S'),
                                            'kwh': float(row['kwhtotal']),
                                        })

            _LOGGER.debug("CLP END")
        except Exception as e:
            await self.hass.services.async_call(
                'persistent_notification',
                'create',
                {
                    'title': f'Error in {self._name} sensor',
                    'message': str(e),
                    'notification_id': f'clp_{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}',
                }
            )

            _LOGGER.error(f"Error updating sensor {self._name}: {e}", exc_info=True)
            self._attr_native_value = None
            self.error = e
            async_call_later(self.hass, self._retry_delay, self.async_update)
