from __future__ import annotations

import datetime
import logging

import async_timeout
import homeassistant.helpers.config_validation as cv
import pytz
import voluptuous as vol
from bs4 import BeautifulSoup
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
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

from .const import (
    CONF_DOMAIN,

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

    vol.Required(CONF_NAME, default='CLP'): cv.string,
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

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=600)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.101 Safari/537.36"

DOMAIN = CONF_DOMAIN


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None,
) -> None:
    session = aiohttp_client.async_get_clientsession(hass)
    csrf_token = await get_csrf_token(session, config.get(CONF_TIMEOUT))
    await login(session, config.get(CONF_USERNAME), config.get(CONF_PASSWORD), csrf_token, config.get(CONF_TIMEOUT))

    async_add_entities(
        [
            CLPSensor(
                sensor_type='main',
                session=session,
                csrf_token=csrf_token,
                name=config.get(CONF_NAME),
                timeout=config.get(CONF_TIMEOUT),
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
                    csrf_token=csrf_token,
                    name=config.get(CONF_RES_NAME),
                    timeout=config.get(CONF_TIMEOUT),
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


async def get_csrf_token(session, timeout):
    async with async_timeout.timeout(timeout):
        response = await session.request(
            "GET",
            "https://services.clp.com.hk/zh/login/index.aspx",
            headers={
                "user-agent": USER_AGENT,
            },
        )
        response.raise_for_status()
        html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')
        csrf_token = soup.select('meta[name="csrf-token"]')[0].attrs['content']
        return csrf_token


async def login(session, username, password, csrf_token, timeout):
    async with async_timeout.timeout(timeout):
        response = await session.request(
            "POST",
            "https://services.clp.com.hk/Service/ServiceLogin.ashx",
            headers={
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "devicetype": "web",
                "html-lang": "zh",
                "user-agent": USER_AGENT,
                "x-csrftoken": csrf_token,
                "x-requested-with": "XMLHttpRequest",
            },
            data={
                "username": username,
                "password": password,
                "rememberMe": "true",
                "loginPurpose": "",
                "magentoToken": "",
                "domeoId": "",
                "domeoPointsBalance": "",
                "domeoPointsNeeded": "",
            },
        )
        response.raise_for_status()


class CLPSensor(SensorEntity):
    _timezone = pytz.timezone('Asia/Hong_Kong')

    def __init__(
            self,
            sensor_type: str,
            session: aiohttp.ClientSession,
            csrf_token: str,
            name: str,
            timeout: int,
            type: str,
            get_acct: bool,
            get_bill: bool,
            get_estimation: bool,
            get_daily: bool,
            get_hourly: bool,
    ) -> None:
        self._sensor_type = sensor_type

        self._session = session
        self._csrf_token = csrf_token
        self._name = name
        self._timeout = timeout

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

        self._state_data_type = None

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

            if self._sensor_type == 'main':
                if self._get_acct:
                    _LOGGER.debug("CLP ACCOUNT")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceGetAccBaseInfoWithBillV2.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "assCA": "",
                                "genPdfFlag": "X",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        due = ''
                        if data['NextDueDate']:
                            due = datetime.datetime.strptime(data['NextDueDate'], '%Y%m%d%H%M%S')

                        self._account = {
                            'number': data['caNo'],
                            'messages': data['alertMsgData'],
                            'outstanding': data['DunningAmount'],
                            'due': due,
                        }

                if self._get_bill or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    _LOGGER.debug("CLP BILL")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceGetBillConsumptionHistory.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "contractAccount": "",
                                "start": dates["today"].strftime("%Y%m%d"),
                                "end": dates["today"].strftime("%Y%m%d"),
                                "mode": "H",
                                "type": "kWh",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['results']:
                            if self._type == '' or self._type.upper() == 'BIMONTHLY':
                                self._state_data_type = 'BIMONTHLY'
                                self._attr_native_value = data['results'][0]['TOT_KWH']
                                self._attr_last_reset = datetime.datetime.strptime(data['results'][0]['PERIOD_LABEL'], '%Y%m%d%H%M%S')
                            if self._get_bill:
                                self._billed = {
                                    "period": datetime.datetime.strptime(data['results'][0]['PERIOD_LABEL'], '%Y%m%d%H%M%S'),
                                    "kwh": data['results'][0]['TOT_KWH'],
                                    "cost": data['results'][0]['TOT_COST'],
                                }

                                self._bills = []
                                for row in data['results']:
                                    self._bills.append({
                                        'start': datetime.datetime.strptime(row['BEGABRPE'], '%Y%m%d'),
                                        'end': datetime.datetime.strptime(row['ENDABRPE'], '%Y%m%d'),
                                        'kwh': row['TOT_KWH'],
                                        'cost': row['TOT_COST'],
                                    })

                if self._get_estimation:
                    _LOGGER.debug("CLP ESTIMATION")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceGetProjectedConsumption.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "contractAccount": "",
                                "isNonAMI": "false",
                                "rateCate": "DOMESTIC",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['ErrorCode'] == '':
                            consumed_start = None
                            consumed_end = None
                            estimation_start = None
                            estimation_end = None

                            if data['currentStartDate']:
                                consumed_start = datetime.datetime.strptime(data['currentStartDate'], '%Y%m%d%H%M%S')

                            if data['currentEndDate']:
                                consumed_end = datetime.datetime.strptime(data['currentEndDate'], '%Y%m%d%H%M%S')

                            if data['projectedStartDate']:
                                estimation_start = datetime.datetime.strptime(data['projectedStartDate'], '%Y%m%d%H%M%S')

                            if data['projectedEndDate']:
                                estimation_end = datetime.datetime.strptime(data['projectedEndDate'], '%Y%m%d%H%M%S')

                            self._unbilled = {
                                "consumed_kwh": float(data['currentConsumption']),
                                "consumed_cost": float(data['currentCost']),
                                "consumed_start": consumed_start,
                                "consumed_end": consumed_end,
                                "estimation_start": estimation_start,
                                "estimation_end": estimation_end,
                                "estimated_kwh": float(data['projectedConsumption']),
                                "estimated_cost": float(data['projectedCost']),
                            }
                        else:
                            self._unbilled = {
                                'error': {
                                    'code': data['ErrorCode'],
                                    'message': data['ErrorMsg'],
                                }
                            }

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug("CLP DAILY")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceGetConsumptionHsitory.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "contractAccount": "",
                                "start": dates["last_month"].strftime("%Y%m%d"),
                                "end": dates["next_month"].strftime("%Y%m%d"),
                                "mode": "D",
                                "type": "kWh",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['results']:
                            if self._type == '' or self._type.upper() == 'DAILY':
                                self._state_data_type = 'DAILY'
                                self._attr_native_value = data['results'][-1]['KWH_TOTAL']
                                self._attr_last_reset = datetime.datetime.strptime(data['results'][-1]['START_DT'], '%Y%m%d%H%M%S')

                            if self._get_daily:
                                self._daily = []
                                for row in data['results']:
                                    start = None
                                    if row['START_DT']:
                                        start = datetime.datetime.strptime(row['START_DT'], '%Y%m%d%H%M%S')

                                    self._daily.append({
                                        'start': start,
                                        'kwh': row['KWH_TOTAL'],
                                    })

                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug("CLP HOURLY")

                    async with async_timeout.timeout(self._timeout):
                        start = dates["yesterday"].strftime("%Y%m%d")
                        end = dates["tomorrow"].strftime("%Y%m%d")

                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceGetConsumptionHsitory.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "contractAccount": "",
                                "start": start,
                                "end": end,
                                "mode": "H",
                                "type": "kWh",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['results']:
                            if self._type == '' or self._type.upper() == 'HOURLY':
                                self._state_data_type = 'HOURLY'
                                self._attr_native_value = data['results'][-1]['KWH_TOTAL']
                                self._attr_last_reset = datetime.datetime.strptime(data['results'][-1]['START_DT'], '%Y%m%d%H%M%S')

                            if self._get_hourly:
                                self._hourly = []

                                for row in data['results']:
                                    self._hourly.append({
                                        'start': datetime.datetime.strptime(row['START_DT'], '%Y%m%d%H%M%S'),
                                        'kwh': row['KWH_TOTAL'],
                                    })

                                self._hourly = sorted(self._hourly, key=lambda x: x['start'], reverse=True)

            elif self._sensor_type == 'renewable_energy':
                _LOGGER.debug("CLP Renewable-Energy")

                if self._get_bill or self._type == '' or self._type.upper() == 'BIMONTHLY':
                    _LOGGER.debug("CLP BILL")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceREGenGraph.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "mode": "B",
                                "startDate": dates["today"].strftime("%m/%d/%Y"),
                                "perCount": "12",
                                "location": "C",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['ConsumptionData']:
                            if self._type == '' or self._type.upper() == 'BIMONTHLY':
                                self._state_data_type = 'BIMONTHLY'
                                self._attr_native_value = data['ConsumptionData'][-1]['KWHTotal']
                                self._attr_last_reset = datetime.datetime.strptime(data['ConsumptionData'][-1]['Enddate'], '%Y%m%d%H%M%S')

                            if self._get_bill:
                                self._bills = []
                                for row in data['ConsumptionData']:
                                    self._bills.append({
                                        'start': datetime.datetime.strptime(row['Startdate'], '%Y%m%d%H%M%S'),
                                        'end': datetime.datetime.strptime(row['Enddate'], '%Y%m%d%H%M%S'),
                                        'kwh': row['KWHTotal'],
                                    })

                if self._get_daily or self._type == '' or self._type.upper() == 'DAILY':
                    _LOGGER.debug("CLP DAILY")
                    async with async_timeout.timeout(self._timeout):
                        response = await self._session.request(
                            "POST",
                            "https://services.clp.com.hk/Service/ServiceREGenGraph.ashx",
                            headers={
                                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                "devicetype": "web",
                                "html-lang": "zh",
                                "user-agent": USER_AGENT,
                                "x-csrftoken": self._csrf_token,
                                "x-requested-with": "XMLHttpRequest",
                            },
                            data={
                                "mode": "D",
                                "startDate": dates["today"].strftime("%m/%d/%Y"),
                                "perCount": "32",
                                "location": "C",
                            },
                        )
                        response.raise_for_status()
                        data = await response.json()

                        _LOGGER.debug(data)

                        if data['ConsumptionData']:
                            if self._type == '' or self._type.upper() == 'DAILY':
                                for row in sorted(data['ConsumptionData'], key=lambda x: x['Startdate'], reverse=True):
                                    if row['ValidateStatus'] == 'Y':
                                        self._state_data_type = 'DAILY'
                                        self._attr_native_value = row['KWHTotal']
                                        self._attr_last_reset = datetime.datetime.strptime(row['Startdate'], '%Y%m%d%H%M%S')
                                        break

                            if self._get_daily:
                                self._daily = []

                                for row in data['ConsumptionData']:
                                    start = None
                                    if row['Startdate']:
                                        start = datetime.datetime.strptime(row['Startdate'], '%Y%m%d%H%M%S')

                                    self._daily.append({
                                        'start': start,
                                        'kwh': row['KWHTotal'],
                                        'validate_status': row['ValidateStatus'],
                                    })

                if self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY':
                    _LOGGER.debug("CLP HOURLY")

                    self._hourly = []
                    async with async_timeout.timeout(self._timeout):
                        for i in range(2):
                            if i == 0:
                                start = dates["today"].strftime("%m/%d/%Y")
                            else:
                                start = dates["yesterday"].strftime("%m/%d/%Y")

                            response = await self._session.request(
                                "POST",
                                "https://services.clp.com.hk/Service/ServiceREGenGraph.ashx",
                                headers={
                                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                    "devicetype": "web",
                                    "html-lang": "zh",
                                    "user-agent": USER_AGENT,
                                    "x-csrftoken": self._csrf_token,
                                    "x-requested-with": "XMLHttpRequest",
                                },
                                data={
                                    "mode": "H",
                                    "startDate": start,
                                    "perCount": "",
                                    "location": "C",
                                },
                            )
                            response.raise_for_status()
                            data = await response.json()

                            _LOGGER.debug(data)

                            if data['ConsumptionData']:
                                self._state_data_type = 'HOURLY'

                                for row in data['ConsumptionData']:
                                    if row['ValidateStatus'] == 'N':
                                        break

                                    start = None
                                    if row['Startdate']:
                                        start = datetime.datetime.strptime(row['Startdate'], '%Y%m%d%H%M%S')

                                    self._hourly.append({
                                        'start': start,
                                        'kwh': row['KWHTotal'],
                                    })

                                self._hourly = sorted(self._hourly, key=lambda x: x['start'], reverse=True)
                                self._attr_native_value = self._hourly[0]['kwh']
                                self._attr_last_reset = self._hourly[0]['start']

            _LOGGER.debug("CLP END")
        except Exception as e:
            _LOGGER.debug(e)
