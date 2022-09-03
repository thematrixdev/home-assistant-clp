from __future__ import annotations

import datetime

import aiohttp
import async_timeout
import homeassistant.helpers.config_validation as cv
import pytz
import voluptuous as vol
from bs4 import BeautifulSoup
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
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_TIMEOUT, default=30): cv.positive_int,
})

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=600)
TIMEOUT = 10


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

    async_add_entities(
        [
            CLPSensor(
                session=session,
                name=name,
                username=username,
                password=password,
                timeout=timeout,
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
    ) -> None:
        self._session = session
        self._name = name
        self._username = username
        self._password = password
        self._timeout = timeout
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = 0
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def name(self) -> str | None:
        return self._name

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        try:
            async with async_timeout.timeout(TIMEOUT):
                response = await self._session.request(
                    "GET",
                    "https://services.clp.com.hk/zh/login/index.aspx",
                    headers={
                        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.101 Safari/537.36",
                    },
                )
                response.raise_for_status()
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                csrf_token = soup.select('meta[name="csrf-token"]')[0].attrs['content']

            async with async_timeout.timeout(TIMEOUT):
                response = await self._session.request(
                    "POST",
                    "https://services.clp.com.hk/Service/ServiceLogin.ashx",
                    headers={
                        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "devicetype": "web",
                        "html-lang": "zh",
                        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.101 Safari/537.36",
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

            async with async_timeout.timeout(TIMEOUT):
                response = await self._session.request(
                    "POST",
                    "https://services.clp.com.hk/Service/ServiceGetConsumptionHsitory.ashx",
                    headers={
                        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "devicetype": "web",
                        "html-lang": "zh",
                        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.101 Safari/537.36",
                        "x-csrftoken": csrf_token,
                        "x-requested-with": "XMLHttpRequest",
                    },
                    data={
                        "contractAccount": "",
                        "start": today,
                        "end": tomorrow,
                        "mode": "H",
                        "type": "kWh",
                    },
                )
                response.raise_for_status()
                data = await response.json()
                self._attr_native_value = data['results'][-1]['KWH_TOTAL']
        except Exception as e:
            pass
