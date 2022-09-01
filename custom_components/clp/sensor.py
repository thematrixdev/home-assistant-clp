from __future__ import annotations

import datetime
import json

import homeassistant.helpers.config_validation as cv
import pytz
import voluptuous as vol
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
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    async_add_entities(
        [
            CLPSensor(
                name=name,
                username=username,
                password=password,
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
        name: str,
        username: str,
        password: str,
    ) -> None:
        self._name = name
        self._username = username
        self._password = password
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = 0
        self._attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def name(self) -> str | None:
        return self._name

    def update(self) -> None:
        options = Options()
        options.headless = True

        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()),
            options=options,
        )
        driver.get("https://services.clp.com.hk/zh/login/index.aspx")

        assert "登入賬戶 - 中電" in driver.title

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.login-rt-loginbtn'))
        )

        btn_login = driver.find_element(
            by=By.CSS_SELECTOR,
            value='button.login-rt-loginbtn',
        )
        btn_login.click()

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.login-password'))
        )

        btn_password = driver.find_element(
            by=By.CSS_SELECTOR,
            value='button.login-password',
        )
        btn_password.click()

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '#personal_user_nametext'))
        )

        input_username = driver.find_element(
            by=By.CSS_SELECTOR,
            value='#personal_user_nametext',
        )
        input_username.send_keys(self._username)

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '#personal_passwordpassword'))
        )

        input_password = driver.find_element(
            by=By.CSS_SELECTOR,
            value='#personal_passwordpassword',
        )
        input_password.send_keys(self._password)

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="passwordLogin_remembercheckbox"]'))
        )

        input_remember = driver.find_element(
            by=By.CSS_SELECTOR,
            value='label[for="passwordLogin_remembercheckbox"]',
        )
        input_remember.click()

        WebDriverWait(driver, 30, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '#passwordLogin button[type="submit"]'))
        )

        btn_signin = driver.find_element(
            by=By.CSS_SELECTOR,
            value='#passwordLogin button[type="submit"]',
        )
        btn_signin.click()

        WebDriverWait(driver, 30, 1).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'meta[name="csrf-token"]'))
        )
        meta_csrf_token = driver.find_element(
            by=By.CSS_SELECTOR,
            value='meta[name="csrf-token"]',
        )
        csrf_token = meta_csrf_token.get_attribute("content")

        today = datetime.datetime.now(pytz.timezone('Asia/Hong_Kong')).strftime("%Y%m%d")
        tomorrow = (datetime.datetime.today() + datetime.timedelta(days=1)).strftime("%Y%m%d")

        jsrequest = '''var xhr = new XMLHttpRequest();
            xhr.open('POST', 'https://services.clp.com.hk/Service/ServiceGetConsumptionHsitory.ashx', false);
            xhr.setRequestHeader('accept', 'application/json, text/javascript, */*; q=0.01');
            xhr.setRequestHeader('content-type', 'application/x-www-form-urlencoded; charset=UTF-8');
            xhr.setRequestHeader('devicetype', 'web');
            xhr.setRequestHeader('html-lang', 'zh');
            xhr.setRequestHeader('x-csrftoken', '{meta_csrf_token}');
            xhr.setRequestHeader('x-requested-with', 'XMLHttpRequest');
            xhr.send('contractAccount=&start={today}&end={tomorrow}&mode=H&type=kWh');
            return xhr.response;'''
        response = driver.execute_script(jsrequest.format(
            meta_csrf_token=csrf_token,
            today=today,
            tomorrow=tomorrow,
        ))

        data = json.loads(response)

        self._attr_native_value = data['results'][-1]['KWH_TOTAL']

        driver.close()
