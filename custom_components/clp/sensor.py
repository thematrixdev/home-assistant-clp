from __future__ import annotations

import datetime
import logging

import aiohttp
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
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

DOMAIN = "CLP"

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_TIMEOUT, default=30): cv.positive_int,
    vol.Optional(CONF_TYPE, default=''): cv.string,
})

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=600)
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.101 Safari/537.36"

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    session = aiohttp_client.async_get_clientsession(hass)
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    timeout = config.get(CONF_TIMEOUT)
    type = config.get(CONF_TYPE)

    async_add_entities(
        [
            CLPSensor(
                session=session,
                name=name,
                username=username,
                password=password,
                timeout=timeout,
                type=type,
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


class CLPSensor(SensorEntity):
    def __init__(
        self,
        session: aiohttp.ClientSession,
        name: str,
        username: str,
        password: str,
        timeout: int,
        type: str,
    ) -> None:
        self._session = session
        self._name = name
        self._username = username
        self._password = password
        self._timeout = timeout
        self._type = type

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL

        self._state_data_type = None

        self._account = None
        self._eco_points = None
        self._bills = None
        self._billed = None
        self._unbilled = None
        self._daily = None
        self._hourly = None

    @property
    def state_class(self) -> SensorStateClass | str | None:
        return SensorStateClass.TOTAL

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "state_data_type": self._state_data_type,
            "account": self._account,
            "eco_points": self._eco_points,
            "bills": self._bills,
            "billed": self._billed,
            "unbilled": self._unbilled,
            "daily": self._daily,
            "hourly": self._hourly,
        }

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        try:
            _LOGGER.debug("CLP BEGIN")

            async with async_timeout.timeout(self._timeout):
                response = await self._session.request(
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

            _LOGGER.debug("CLP LOGIN")
            async with async_timeout.timeout(self._timeout):
                response = await self._session.request(
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
                        "username": self._username,
                        "password": self._password,
                        "rememberMe": "true",
                        "loginPurpose": "",
                        "magentoToken": "",
                        "domeoId": "",
                        "domeoPointsBalance": "",
                        "domeoPointsNeeded": "",
                    },
                )
                response.raise_for_status()

            today = datetime.datetime.now(pytz.timezone('Asia/Hong_Kong')).strftime("%Y%m%d")
            tomorrow = (datetime.datetime.today() + datetime.timedelta(days=1)).strftime("%Y%m%d")
            this_month = datetime.datetime.now(pytz.timezone('Asia/Hong_Kong')).replace(day=1).strftime("%Y%m%d")
            next_month = (datetime.datetime.now(pytz.timezone('Asia/Hong_Kong')).replace(day=1) + relativedelta.relativedelta(months=1)).strftime("%Y%m%d")

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
                        "x-csrftoken": csrf_token,
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

                self._account = {
                    'number': data['caNo'],
                    'messages': data['alertMsgData'],
                    'outstanding': data['DunningAmount'],
                    'due': datetime.datetime.strptime(data['NextDueDate'], '%Y%m%d'),
                }

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
                        "x-csrftoken": csrf_token,
                        "x-requested-with": "XMLHttpRequest",
                    },
                    data={
                        "contractAccount": "",
                        "start": today,
                        "end": today,
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
                        "x-csrftoken": csrf_token,
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

                if data['ErrorCode'] != '':
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

            _LOGGER.debug("CLP ECO-POINTS")
            async with async_timeout.timeout(self._timeout):
                response = await self._session.request(
                    "POST",
                    "https://services.clp.com.hk/Service/ServiceEcoPoints.ashx",
                    headers={
                        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "devicetype": "web",
                        "html-lang": "zh",
                        "user-agent": USER_AGENT,
                        "x-csrftoken": csrf_token,
                        "x-requested-with": "XMLHttpRequest",
                    },
                    data={
                        "contractAccount": self._account['number'],
                    },
                )
                response.raise_for_status()
                data = await response.json()

                _LOGGER.debug(data)

                expiry = None
                if data['ExpiryDatetime']:
                    expiry = datetime.datetime.strptime(data['ExpiryDatetime'], '%Y%m%d%H%M%S')

                self._eco_points = {
                    "balance": data['EP_Balance'],
                    "expiry": expiry,
                }

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
                        "x-csrftoken": csrf_token,
                        "x-requested-with": "XMLHttpRequest",
                    },
                    data={
                        "contractAccount": "",
                        "start": this_month,
                        "end": next_month,
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

                    self._daily = []
                    for row in data['results']:
                        start = None
                        if row['START_DT']:
                            start = datetime.datetime.strptime(row['START_DT'], '%Y%m%d%H%M%S')

                        self._daily.append({
                            'start': start,
                            'kwh': row['KWH_TOTAL'],
                        })

            _LOGGER.debug("CLP HOURLY")
            async with async_timeout.timeout(self._timeout):
                for i in range(2):
                    if i == 0:
                        start = today
                        end = tomorrow
                    else:
                        start = (datetime.datetime.today() + datetime.timedelta(days=-1)).strftime("%Y%m%d")
                        end = today

                    response = await self._session.request(
                        "POST",
                        "https://services.clp.com.hk/Service/ServiceGetConsumptionHsitory.ashx",
                        headers={
                            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "devicetype": "web",
                            "html-lang": "zh",
                            "user-agent": USER_AGENT,
                            "x-csrftoken": csrf_token,
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

                        self._hourly = []
                        for row in data['results']:
                            start = None
                            if row['START_DT']:
                                start = datetime.datetime.strptime(row['START_DT'], '%Y%m%d%H%M%S')

                            self._hourly.append({
                                'start': start,
                                'kwh': row['KWH_TOTAL'],
                            })

                        break

            _LOGGER.debug("CLP END")
        except Exception as e:
            print(e, flush=True)
