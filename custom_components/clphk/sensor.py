from __future__ import annotations

import asyncio
import datetime
import json as jsonlib
import logging
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import relativedelta
from curl_cffi.requests import AsyncSession

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:
    StatisticMeanType = None
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
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
    EntityCategory,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

from .const import (
    CONF_DOMAIN,
    DEFAULT_TIER_LIMITS,
    DEFAULT_TIER_RATES,
    calculate_residential_bill,
    calculate_tier_consumption,
    is_auth_failure,
    is_transient,
    parse_comma_floats,
    parse_datetime,
    parse_refresh_tokens,
    reconcile_tariff_tiers,
    safe_float,
    CONF_GET_ACCT,
    CONF_GET_BILL,
    CONF_GET_ESTIMATION,
    CONF_GET_BIMONTHLY,
    CONF_GET_DAILY,
    CONF_GET_HOURLY,
    CONF_GET_HOURLY_DAYS,
    CONF_RES_ENABLE,
    CONF_CUSTOM_FUEL_CENTS,
    CONF_CUSTOM_FIXED_RATE,
    CONF_CUSTOM_SUBSIDY,
    CONF_CUSTOM_RATE_ENTITY,
    CONF_CUSTOM_TIER_RATES,
    CONF_CUSTOM_TIER_LIMITS,
)

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=300)
DAILY_TASK_INTERVAL = datetime.timedelta(hours=12)
HOURLY_TASK_INTERVAL = datetime.timedelta(minutes=60)

DOMAIN = CONF_DOMAIN


class FatalAuthError(Exception):
    """Non-recoverable auth error that requires reconfiguration."""


API_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
    "Referer": "https://www.clp.com.hk/",
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

    entry_id = discovery_info.get("entry_id")
    domain_data = hass.data.setdefault(DOMAIN, {})
    if entry_id and entry_id in domain_data:
        token_bucket = domain_data[entry_id]
    else:
        token_bucket = domain_data

    for k in ("access_token", "refresh_token", "access_token_expiry_time"):
        if discovery_info.get(k) is not None and discovery_info.get(k) != "":
            token_bucket[k] = discovery_info.get(k)
    if "token_lock" not in token_bucket:
        token_bucket["token_lock"] = asyncio.Lock()

    main_sensor = CLPSensor(
        hass=hass,
        sensor_type="main",
        name=discovery_info.get(CONF_NAME, "CLP"),
        timeout=int(float(discovery_info.get(CONF_TIMEOUT, 30) or 30)),
        type=discovery_info.get(CONF_TYPE, ""),
        get_acct=discovery_info.get(CONF_GET_ACCT, False),
        get_bill=discovery_info.get(CONF_GET_BILL, False),
        get_estimation=discovery_info.get(CONF_GET_ESTIMATION, False),
        get_bimonthly=discovery_info.get(CONF_GET_BIMONTHLY, False),
        get_daily=discovery_info.get(CONF_GET_DAILY, False),
        get_hourly=discovery_info.get(CONF_GET_HOURLY, False),
        get_hourly_days=int(float(discovery_info.get(CONF_GET_HOURLY_DAYS, 2) or 2)),
        custom_fuel_cents=discovery_info.get(CONF_CUSTOM_FUEL_CENTS),
        custom_fixed_rate=discovery_info.get(CONF_CUSTOM_FIXED_RATE),
        custom_subsidy=discovery_info.get(CONF_CUSTOM_SUBSIDY),
        custom_rate_entity=discovery_info.get(CONF_CUSTOM_RATE_ENTITY),
        custom_tier_rates=discovery_info.get(CONF_CUSTOM_TIER_RATES),
        custom_tier_limits=discovery_info.get(CONF_CUSTOM_TIER_LIMITS),
        entry_id=entry_id,
    )

    if entry_id and entry_id in domain_data and isinstance(domain_data[entry_id], dict):
        domain_data[entry_id].setdefault("sensors", []).append(main_sensor)
    else:
        domain_data.setdefault("sensors", []).append(main_sensor)
    entities: list[SensorEntity] = [main_sensor]

    # Add child sensors for main sensor
    sub_sensor_configs = [
        ("projected_cost", "Projected Cost", SensorDeviceClass.MONETARY, "HKD", None, None),
        ("current_consumption", "Current Period Consumption", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, None, None),
        ("projected_consumption", "Projected Consumption", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, None, None),
        ("last_bill", "Last Bill Amount", SensorDeviceClass.MONETARY, "HKD", None, None),
        ("outstanding", "Outstanding Amount", SensorDeviceClass.MONETARY, "HKD", None, None),
        ("base_tariff", "Base Tariff Rate", None, "HKD/kWh", None, None),
        ("fuel_adjustment", "Fuel Clause Adjustment", None, "HKD/kWh", None, None),
        ("tariff_rate", "Projected Effective Tariff Rate", None, "HKD/kWh", None, None),
        ("tier_consumption", "Tier Consumption", None, None, None, EntityCategory.DIAGNOSTIC),
        ("tier_rates", "Tier Rates", None, "HKD/kWh", None, EntityCategory.DIAGNOSTIC),
    ]
    for sub_key, sub_name, dev_class, unit, state_class, ent_cat in sub_sensor_configs:
        entities.append(
            CLPSubSensor(
                parent=main_sensor,
                sub_key=sub_key,
                name=f"{main_sensor.name} {sub_name}",
                device_class=dev_class,
                unit_of_measurement=unit,
                state_class=state_class,
                entity_category=ent_cat,
            )
        )

    if discovery_info.get(CONF_RES_ENABLE, False):
        res_name = f"{main_sensor.name} Renewable Energy"
        res_sensor = CLPSensor(
            hass=hass,
            sensor_type="renewable_energy",
            name=res_name,
            timeout=int(float(discovery_info.get(CONF_TIMEOUT, 30) or 30)),
            type=discovery_info.get(CONF_TYPE, ""),
            get_acct=False,
            get_bill=True,
            get_estimation=False,
            get_bimonthly=True,
            get_daily=True,
            get_hourly=True,
            get_hourly_days=int(float(discovery_info.get(CONF_GET_HOURLY_DAYS, 2) or 2)),
            entry_id=entry_id,
        )
        if entry_id and entry_id in domain_data and isinstance(domain_data[entry_id], dict):
            domain_data[entry_id].setdefault("sensors", []).append(res_sensor)
        else:
            domain_data.setdefault("sensors", []).append(res_sensor)
        entities.append(res_sensor)

    async_add_entities(entities, update_before_add=True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    merged = {**config_entry.data, **config_entry.options, "entry_id": config_entry.entry_id}
    await async_setup_platform(
        hass,
        {},
        async_add_entities,
        discovery_info=merged,
    )


def handle_errors(func):
    """Record a fetch failure on the entity and swallow it so sibling fetches in
    the same update cycle still run. FatalAuthError is re-raised so async_update
    can stop the cycle. Retries are driven by Home Assistant's polling."""
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except FatalAuthError:
            raise
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            self._error = str(e)
            _LOGGER.warning("%s: Connection temporarily failed in %s: %s", self._name, func.__name__, e)
            return None
        except Exception as e:
            self._error = str(e)
            _LOGGER.error("%s ERROR in %s: %s", self._name, func.__name__, e, exc_info=True)
            return None

    return wrapper


class CLPSensor(SensorEntity):
    _timezone = ZoneInfo("Asia/Hong_Kong")

    def __init__(
        self,
        hass: HomeAssistant,
        sensor_type: str,
        name: str,
        timeout: int,
        type: str = None,
        get_acct: bool = False,
        get_bill: bool = False,
        get_estimation: bool = False,
        get_bimonthly: bool = False,
        get_daily: bool = False,
        get_hourly: bool = False,
        get_hourly_days: int = 2,
        custom_fuel_cents: float | None = None,
        custom_fixed_rate: float | None = None,
        custom_subsidy: float | None = None,
        custom_rate_entity: str | None = None,
        custom_tier_rates: str | list[float] | None = None,
        custom_tier_limits: str | list[float] | None = None,
        entry_id: str | None = None,
    ) -> None:
        _LOGGER.debug("[SENSOR INIT] type=%s, name=%s, entry_id=%s", sensor_type, name, entry_id)
        self.hass = hass
        self._sensor_type = sensor_type
        self._name = name
        self._timeout = timeout
        self._type = type or ""
        self._entry_id = entry_id
        self._get_acct = get_acct
        self._get_bill = get_bill
        self._get_estimation = get_estimation
        self._get_bimonthly = get_bimonthly
        self._get_daily = get_daily
        self._get_hourly = get_hourly
        self._get_hourly_days = get_hourly_days
        self._custom_fuel_cents = safe_float(custom_fuel_cents)
        self._custom_fixed_rate = safe_float(custom_fixed_rate)
        self._custom_subsidy = safe_float(custom_subsidy)
        self._custom_rate_entity = str(custom_rate_entity).strip() if custom_rate_entity else None
        self._custom_tier_rates = parse_comma_floats(custom_tier_rates)
        self._custom_tier_limits = parse_comma_floats(custom_tier_limits)
        self._latest_tariff = {}
        self._tariff_last_fetch_time = None
        self._account_number = None
        self._state_data_type = None
        self._error = None
        self._fatal_error = False
        self._daily_backfill_done = False

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        # Interval readings must not be marked as TOTAL to prevent corrupt recorder jumps
        self._attr_state_class = None
        self._attr_name = name
        self._attr_unique_id = f"clphk_{sensor_type}_{name.replace(' ', '_').lower()}"

        self._account = None
        self._bills = None
        self._estimation = None
        self._bimonthly = None
        self._daily = None
        self._daily_totals = {}
        self._hourly = None

        self._last_reset = None
        self._tariff_last_fetch_time = None
        self._account_last_fetch_time = None
        self._bill_last_fetch_time = None
        self._estimation_last_fetch_time = None
        self._bimonthly_last_fetch_time = None
        self._daily_last_fetch_time = None
        self._hourly_last_fetch_time = None
        self._single_task_last_fetch_time = None
        self._no_account_warned = False
        self._multi_account_warned = False
        self._sub_sensors: list[CLPSubSensor] = []

    @property
    def available(self) -> bool:
        return bool(self._access_token) and not self._fatal_error

    @property
    def sensor_type(self) -> str:
        return self._sensor_type

    @property
    def estimation(self) -> dict | None:
        return self._estimation

    @property
    def bills(self) -> dict | None:
        return self._bills

    @property
    def account(self) -> dict | None:
        return self._account

    @property
    def bimonthly(self) -> list | None:
        return self._bimonthly

    @property
    def latest_tariff(self) -> dict:
        return self._latest_tariff

    @property
    def custom_fuel_cents(self) -> float | None:
        return self._custom_fuel_cents

    @property
    def custom_fixed_rate(self) -> float | None:
        return self._custom_fixed_rate

    @property
    def custom_subsidy(self) -> float | None:
        return self._custom_subsidy

    @property
    def custom_rate_entity(self) -> str | None:
        return self._custom_rate_entity

    @property
    def custom_tier_rates(self) -> list[float] | None:
        return self._custom_tier_rates

    @property
    def custom_tier_limits(self) -> list[float] | None:
        return self._custom_tier_limits

    def get_effective_tiers(self) -> tuple[list[float], list[float]]:
        """Return harmonized (rates, limits) adaptive to any number of tiers N."""
        tariff = self._latest_tariff or {}
        base_rates = tariff.get("tier_rates")
        base_limits = tariff.get("tier_limits")
        return reconcile_tariff_tiers(
            custom_rates=self._custom_tier_rates,
            custom_limits=self._custom_tier_limits,
            base_rates=base_rates,
            base_limits=base_limits,
        )

    def get_effective_tier_rates(self) -> list[float]:
        rates, _ = self.get_effective_tiers()
        return rates

    def get_effective_tier_limits(self) -> list[float]:
        _, limits = self.get_effective_tiers()
        return limits

    async def async_fetch_monthly_tariff(self, force: bool = False) -> dict:
        """Fetch latest residential tariff rates from CLP official API."""
        now = datetime.datetime.now(self._timezone)
        current_ym = (now.year, now.month)
        if not force and self._latest_tariff and self._latest_tariff.get("year_month") == current_ym:
            return self._latest_tariff

        start_date = f"{now.year}{now.month:02d}01000000"
        try:
            async with AsyncSession(impersonate="chrome131") as session:
                headers = {
                    "configPath": "/content/dam/clphk/config/calculator.properties",
                    "Referer": "https://www.clp.com.hk/zh/residential/bills-payment-tariffs-residential/bill-calculator",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json;charset=UTF-8",
                }
                body = {
                    "StartDate": start_date,
                    "TariffType": "DT",
                    "OnPeakPeriod": "0000099999",
                    "NoOfDays": "60",
                }
                resp = await session.post(
                    "https://www.clp.com.hk/bin/calculator/tariff/residential",
                    headers=headers,
                    json=body,
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    fuel_rate = 39.4
                    special_rebate = 0.0
                    energy_charge = 0.945
                    rebate = 0.172
                    tier_rates = []
                    tier_limits = []
                    energy_items = [x for x in data.get("results", []) if x.get("ChargeType") == "Energy charge"]
                    for idx, item in enumerate(energy_items):
                        r = float(item.get("Rate", 0))
                        tier_rates.append(round(r, 4))
                        if idx < len(energy_items) - 1:
                            c = float(item.get("Consumption", 0))
                            tier_limits.append(c)

                    for item in data.get("results", []):
                        ct = item.get("ChargeType")
                        r = float(item.get("Rate", 0))
                        if ct == "Fuel cost adjustment":
                            fuel_rate = round(r * 100, 2)
                        elif ct == "Special fuel rebate":
                            special_rebate = round(abs(r) * 100, 2)
                        elif ct == "Energy charge" and not energy_charge:
                            energy_charge = r
                        elif ct == "Energy saving rebate":
                            rebate = abs(r)

                    self._latest_tariff = {
                        "year_month": current_ym,
                        "fuel_cents": fuel_rate,
                        "special_fuel_rebate_cents": special_rebate,
                        "energy_charge": tier_rates[0] if tier_rates else energy_charge,
                        "tier_rates": tier_rates or list(DEFAULT_TIER_RATES),
                        "tier_limits": tier_limits if tier_rates else list(DEFAULT_TIER_LIMITS),
                        "rebate": rebate,
                        "last_synced": now.isoformat(),
                    }
                    self._tariff_last_fetch_time = now
                    _LOGGER.debug(
                        "[TARIFF] Successfully fetched CLP tariff for %04d-%02d: fuel=%.2f¢, special_rebate=%.2f¢, tiers=%s",
                        now.year, now.month, fuel_rate, special_rebate, tier_rates,
                    )
                    return self._latest_tariff
        except Exception as ex:
            _LOGGER.debug("[TARIFF] Could not fetch latest CLP tariff from official calculator API: %s", ex)

        if not self._latest_tariff:
            self._latest_tariff = {
                "year_month": current_ym,
                "fuel_cents": 47.4 if (now.year == 2026 and now.month >= 11) else 39.4,
                "special_fuel_rebate_cents": 0.0,
                "energy_charge": 0.945,
                "tier_rates": [0.945, 1.079, 1.237, 1.545, 1.774, 1.878, 1.890],
                "tier_limits": [400.0, 600.0, 800.0, 800.0, 800.0, 800.0],
                "rebate": 0.172,
                "last_synced": None,
            }
            self._tariff_last_fetch_time = now
        return self._latest_tariff

    def get_effective_tariff_rate(self) -> float:
        """Return effective tariff rate (HKD/kWh) considering user custom overrides and official data."""
        # 1. Custom fixed rate
        if self._custom_fixed_rate is not None and self._custom_fixed_rate > 0:
            return round(self._custom_fixed_rate, 4)

        # 2. Custom rate entity
        if self._custom_rate_entity:
            state_obj = self.hass.states.get(self._custom_rate_entity)
            if state_obj and state_obj.state not in (None, "unknown", "unavailable"):
                try:
                    val = float(state_obj.state)
                    if val > 0:
                        return round(val, 4)
                except (ValueError, TypeError):
                    pass

        tariff = self._latest_tariff or {}
        fuel_cents = self._custom_fuel_cents if (self._custom_fuel_cents and self._custom_fuel_cents > 0) else tariff.get("fuel_cents", 47.4)
        special_rebate = tariff.get("special_fuel_rebate_cents", 0.0)
        subsidy = self._custom_subsidy or 0.0
        tier_rates = self.get_effective_tier_rates()
        tier_limits = self.get_effective_tier_limits()
        has_custom_tier = bool(self._custom_tier_rates or self._custom_tier_limits)

        # 3. If custom fuel cents, subsidy, or custom tiers are set, calculate dynamically with official formula
        est = self._estimation or {}
        if (self._custom_fuel_cents and self._custom_fuel_cents > 0) or subsidy > 0 or has_custom_tier:
            curr_kwh = est.get("current_consumption") or est.get("estimation_consumption") or 300.0
            calc = calculate_residential_bill(
                kwh=curr_kwh,
                days=60,
                fuel_cents=fuel_cents,
                special_fuel_rebate_cents=special_rebate,
                subsidy=subsidy,
                tier_limits=tier_limits,
                tier_rates=tier_rates,
            )
            return calc.get("effective_rate")

        # 4. CLP official server estimation
        p_cost = est.get("estimation_cost")
        p_kwh = est.get("estimation_consumption")
        if p_cost is not None and p_kwh and p_kwh > 0:
            return round(p_cost / p_kwh, 4)

        # 5. Previous bill
        bill_list = (self._bills or {}).get("bill") if isinstance(self._bills, dict) else (self._bills or [])
        bimonthly = self._bimonthly or []
        if bill_list and bimonthly:
            b_kwh = bimonthly[0].get("kwh")
            b_total = bill_list[0].get("total")
            if b_kwh and b_kwh > 0 and b_total is not None and b_total > 0:
                return round(b_total / b_kwh, 4)

        # 6. Fallback formula
        curr_kwh = est.get("current_consumption") or 300.0
        calc = calculate_residential_bill(
            kwh=curr_kwh,
            days=60,
            fuel_cents=fuel_cents,
            special_fuel_rebate_cents=special_rebate,
            subsidy=subsidy,
            tier_limits=tier_limits,
            tier_rates=tier_rates,
        )
        return calc.get("effective_rate")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._name,
            manufacturer="CLP Power Hong Kong",
            model="Electricity Account",
            configuration_url="https://www.clp.com.hk",
        )

    def register_sub_sensor(self, sensor: CLPSubSensor) -> None:
        if sensor not in self._sub_sensors:
            self._sub_sensors.append(sensor)

    def unregister_sub_sensor(self, sensor: CLPSubSensor) -> None:
        if sensor in self._sub_sensors:
            self._sub_sensors.remove(sensor)

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return self._attr_name

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def _token_state(self):
        domain_data = self.hass.data.get(DOMAIN, {})
        if self._entry_id and self._entry_id in domain_data and isinstance(domain_data[self._entry_id], dict):
            return domain_data[self._entry_id]
        return domain_data

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
    def extra_state_attributes(self) -> dict:
        attr = {
            "state_data_type": self._state_data_type,
            "error": self._error,
        }
        if getattr(self, "_last_reset", None):
            attr["last_reset"] = self._last_reset.isoformat() if hasattr(self._last_reset, "isoformat") else str(self._last_reset)

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
        if not self._access_token and 'refresh_token' not in url:
            raise Exception("Problematic authorization. Please configure credentials again.")

        merged_headers = dict(API_DEFAULT_HEADERS)
        if json is not None:
            merged_headers["Content-Type"] = "application/json"
        if headers:
            merged_headers.update(headers)

        async with asyncio.timeout(self._timeout):
            async with AsyncSession() as session:
                response = await session.request(
                    method,
                    url,
                    headers=merged_headers,
                    params=params,
                    json=json,
                    impersonate="chrome",
                )

        status = response.status_code

        if status >= 400:
            error_content = response.text or ""
            try:
                error_data = jsonlib.loads(error_content)
            except (ValueError, TypeError):
                error_data = None

            error_code = error_data.get("code") if isinstance(error_data, dict) else None
            _LOGGER.error("HTTP %s for %s (code=%s)", status, url, error_code)

            if 400 <= status < 500:
                should_refresh = (
                    retry_on_expired
                    and "refresh_token" not in url
                    and self._refresh_token
                    and (headers or {}).get("Authorization")
                    and (
                        error_code in (906, 100001)
                        or (status == 403 and error_data is None)
                    )
                )
                if should_refresh:
                    _LOGGER.debug(
                        "Access token likely expired (status=%s, code=%s). Refreshing and retrying.",
                        status, error_code,
                    )
                    stale_token = (headers or {}).get("Authorization")
                    await self._refresh_access_token(stale_access_token=stale_token)
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

                if is_auth_failure(status, error_code):
                    await self._handle_auth_failure(status, error_content or "")
                    raise FatalAuthError(
                        f"CLPHK authentication failed (HTTP {status}, code {error_code}); tokens cleared."
                    )

                raise Exception(f"CLPHK API error: HTTP {status} for {url} (code {error_code})")

            raise Exception(f"CLPHK API error: HTTP {status} for {url}")

        try:
            response_data = response.json()
        except Exception:
            _LOGGER.error("RESPONSE %s for %s: unreadable or non-JSON body", status, url)
            raise

        if not response_data or 'data' not in response_data:
            _LOGGER.error("RESPONSE %s for %s: missing 'data'", status, url)
            raise ValueError('Invalid response data')

        _LOGGER.debug("RESPONSE %s for %s", status, url)
        return response_data

    async def _refresh_access_token(self, stale_access_token=None):
        """Refresh access token using stored refresh token and persist it."""
        token_state = self._token_state
        token_lock = token_state.get("token_lock") if token_state else None
        if token_lock is None:
            raise FatalAuthError("CLPHK token state/lock unavailable.")

        async with token_lock:
            if stale_access_token is not None and self._access_token != stale_access_token:
                if self._access_token is None:
                    raise FatalAuthError("CLPHK auth cleared by a concurrent failure; aborting refresh.")
                _LOGGER.debug("Access token already refreshed by another task; skipping refresh.")
                return

            if not self._refresh_token:
                raise Exception("No refresh token available")

            refresh_headers = dict(API_DEFAULT_HEADERS)
            refresh_headers["Content-Type"] = "application/json"

            async with asyncio.timeout(self._timeout):
                async with AsyncSession() as session:
                    response = await session.request(
                        "POST",
                        "https://api.clp.com.hk/ts1/ms/profile/identity/manage/account/refresh_token",
                        headers=refresh_headers,
                        json={"refreshToken": self._refresh_token},
                        impersonate="chrome",
                    )
            response_text = response.text or ""
            status = response.status_code

            if is_transient(status):
                raise Exception(f"Refresh token request temporarily failed with {status}")
            if 400 <= status < 500:
                await self._handle_auth_failure(status, response_text)
                raise FatalAuthError("Refresh token invalid/expired. Please reconfigure tokens.")
            if status >= 500:
                raise Exception(f"Refresh token request failed with {status}")

            try:
                response_json = jsonlib.loads(response_text)
            except jsonlib.JSONDecodeError as ex:
                raise Exception(f"Refresh token response is not JSON: {response_text[:200]}") from ex

            tokens = parse_refresh_tokens(response_json)
            if tokens is None:
                await self._handle_auth_failure(status, response_text, detail="missing token fields")
                raise FatalAuthError("Refresh response missing tokens; integration stopped.")

            self._access_token, self._refresh_token, self._access_token_expiry_time = tokens

            _LOGGER.debug("[SENSOR UPDATE] Persisting refreshed tokens to config entry.")
            target_entry = None
            if self._entry_id:
                target_entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if not target_entry:
                entries = self.hass.config_entries.async_entries(DOMAIN)
                target_entry = entries[0] if entries else None

            if target_entry:
                data = dict(target_entry.data)
                data["access_token"] = self._access_token
                data["refresh_token"] = self._refresh_token
                data["access_token_expiry_time"] = self._access_token_expiry_time
                self.hass.config_entries.async_update_entry(target_entry, data=data)

    async def _handle_auth_failure(self, status: int, body: str, detail: str = None):
        """Clear tokens, notify frontend, and stop integration on an auth failure."""
        self._fatal_error = True
        self._account_number = None
        self._access_token = None
        self._refresh_token = None
        self._access_token_expiry_time = None

        target_entry = None
        if self._entry_id:
            target_entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if not target_entry:
            entries = self.hass.config_entries.async_entries(DOMAIN)
            target_entry = entries[0] if entries else None

        if target_entry:
            data = dict(target_entry.data)
            data["access_token"] = ""
            data["refresh_token"] = ""
            data["access_token_expiry_time"] = ""
            self.hass.config_entries.async_update_entry(target_entry, data=data)

        reason = f" ({detail})" if detail else ""
        message = (
            f"CLPHK authentication failed{reason} with HTTP {status}. "
            "Tokens were cleared and the integration was stopped. "
            "Please re-authenticate your CLP account."
        )
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "CLPHK Authentication Failed",
                    "message": message,
                    "notification_id": f"clphk_auth_failed_{self._entry_id or 'default'}",
                },
                blocking=False,
            )
        except Exception:
            _LOGGER.warning("Failed to create persistent notification for CLPHK auth failure.")

        if target_entry:
            try:
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "reauth", "entry_id": target_entry.entry_id},
                        data=target_entry.data,
                    )
                )
            except Exception as ex:
                _LOGGER.debug("Could not start reauth flow: %s", ex)

    async def _import_hourly_statistics(self, hourly_records: list[dict]):
        """Import raw hourly energy data directly into Home Assistant Recorder Statistics."""
        if not hourly_records:
            return

        statistic_id = f"{DOMAIN}:{self._sensor_type}_hourly_energy"

        # 1. Deduplicate per hour in UTC
        raw_by_utc: dict[datetime.datetime, float] = {}
        for record in hourly_records:
            dt = record.get("start")
            kwh = record.get("kwh")
            if not dt or kwh is None:
                continue

            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                dt_utc = dt.astimezone(datetime.timezone.utc)
            else:
                dt_local = dt.replace(tzinfo=self._timezone)
                dt_utc = dt_local.astimezone(datetime.timezone.utc)

            dt_utc = dt_utc.replace(minute=0, second=0, microsecond=0)
            raw_by_utc[dt_utc] = round(kwh, 4)

        if not raw_by_utc:
            return

        all_utc_timestamps = sorted(raw_by_utc.keys())
        earliest_ts = all_utc_timestamps[0].timestamp()

        # 2. Query base sum before earliest_ts from recorder
        base_sum = 0.0
        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 500, statistic_id, True, {"sum", "state"}
            )
            if last_stats and statistic_id in last_stats:
                found = False
                for stat in last_stats[statistic_id]:
                    s_time = stat.get("start")
                    rec_ts = float(s_time) if isinstance(s_time, (int, float)) else (s_time.timestamp() if hasattr(s_time, "timestamp") else None)
                    if rec_ts is not None and rec_ts < earliest_ts:
                        base_sum = stat.get("sum") or 0.0
                        found = True
                        break
                if not found and last_stats[statistic_id]:
                    # Keep continuity if records exist but all are within the window
                    oldest = min(
                        last_stats[statistic_id],
                        key=lambda x: x.get("start") if isinstance(x.get("start"), (int, float)) else (x.get("start").timestamp() if hasattr(x.get("start"), "timestamp") else 0),
                    )
                    o_sum = oldest.get("sum") or 0.0
                    o_state = oldest.get("state") or 0.0
                    base_sum = max(0.0, round(o_sum - o_state, 4))
        except Exception as ex:
            _LOGGER.debug("Could not query base statistics for %s: %s", statistic_id, ex)

        statistics: list[StatisticData] = []
        running_sum = base_sum
        for ts in all_utc_timestamps:
            kwh = raw_by_utc[ts]
            running_sum = round(running_sum + kwh, 4)
            statistics.append(
                StatisticData(
                    start=ts,
                    state=kwh,
                    sum=running_sum,
                )
            )

        meta_kwargs: dict = {
            "has_mean": False,
            "has_sum": True,
            "name": f"{self._name} Hourly Energy (for Energy Dashboard)",
            "source": DOMAIN,
            "statistic_id": statistic_id,
            "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        }
        if StatisticMeanType is not None:
            meta_kwargs["mean_type"] = StatisticMeanType.NONE
            meta_kwargs["unit_class"] = "energy"

        metadata = StatisticMetaData(**meta_kwargs)
        async_add_external_statistics(self.hass, metadata, statistics)

        # Import hourly cost statistics
        effective_rate = self.get_effective_tariff_rate()
        statistic_cost_id = f"{DOMAIN}:{self._sensor_type}_hourly_cost"
        base_cost_sum = 0.0
        try:
            last_cost_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 500, statistic_cost_id, True, {"sum", "state"}
            )
            if last_cost_stats and statistic_cost_id in last_cost_stats:
                found_cost = False
                for stat in last_cost_stats[statistic_cost_id]:
                    s_time = stat.get("start")
                    rec_ts = float(s_time) if isinstance(s_time, (int, float)) else (s_time.timestamp() if hasattr(s_time, "timestamp") else None)
                    if rec_ts is not None and rec_ts < earliest_ts:
                        base_cost_sum = stat.get("sum") or 0.0
                        found_cost = True
                        break
                if not found_cost and last_cost_stats[statistic_cost_id]:
                    oldest_c = min(
                        last_cost_stats[statistic_cost_id],
                        key=lambda x: x.get("start") if isinstance(x.get("start"), (int, float)) else (x.get("start").timestamp() if hasattr(x.get("start"), "timestamp") else 0),
                    )
                    oc_sum = oldest_c.get("sum") or 0.0
                    oc_state = oldest_c.get("state") or 0.0
                    base_cost_sum = max(0.0, round(oc_sum - oc_state, 4))
        except Exception as ex:
            _LOGGER.debug("Could not query base cost statistics for %s: %s", statistic_cost_id, ex)

        cost_statistics: list[StatisticData] = []
        running_cost_sum = base_cost_sum
        for ts in all_utc_timestamps:
            kwh = raw_by_utc[ts]
            cost = round(kwh * effective_rate, 4)
            running_cost_sum = round(running_cost_sum + cost, 4)
            cost_statistics.append(
                StatisticData(
                    start=ts,
                    state=cost,
                    sum=running_cost_sum,
                )
            )

        meta_cost_kwargs: dict = {
            "has_mean": False,
            "has_sum": True,
            "name": f"{self._name} Hourly Cost",
            "source": DOMAIN,
            "statistic_id": statistic_cost_id,
            "unit_of_measurement": "HKD",
        }
        if StatisticMeanType is not None:
            meta_cost_kwargs["mean_type"] = StatisticMeanType.NONE
            meta_cost_kwargs["unit_class"] = None

        metadata_cost = StatisticMetaData(**meta_cost_kwargs)
        async_add_external_statistics(self.hass, metadata_cost, cost_statistics)

    async def _import_daily_statistics(self, daily_records: list[dict]):
        """Import official daily energy data directly into Home Assistant Recorder Statistics."""
        if not daily_records:
            return

        statistic_id = f"{DOMAIN}:{self._sensor_type}_daily_energy"

        daily_by_utc: dict[datetime.datetime, float] = {}
        for record in daily_records:
            start_str = str(record.get("startDate") or record.get("startdate") or "")
            kwh = safe_float(record.get("kwhTotal"))
            if len(start_str) < 8 or kwh is None:
                continue

            dt = parse_datetime(start_str[:8] + "000000", "%Y%m%d%H%M%S")
            if not dt:
                continue

            dt_local = dt.replace(tzinfo=self._timezone)
            dt_utc = dt_local.astimezone(datetime.timezone.utc)
            dt_utc = dt_utc.replace(minute=0, second=0, microsecond=0)
            daily_by_utc[dt_utc] = round(kwh, 4)

        if not daily_by_utc:
            return

        all_utc_timestamps = sorted(daily_by_utc.keys())
        earliest_ts = all_utc_timestamps[0].timestamp()

        base_sum = 0.0
        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 500, statistic_id, True, {"sum", "state"}
            )
            if last_stats and statistic_id in last_stats:
                found = False
                for stat in last_stats[statistic_id]:
                    s_time = stat.get("start")
                    rec_ts = float(s_time) if isinstance(s_time, (int, float)) else (s_time.timestamp() if hasattr(s_time, "timestamp") else None)
                    if rec_ts is not None and rec_ts < earliest_ts:
                        base_sum = stat.get("sum") or 0.0
                        found = True
                        break
                if not found and last_stats[statistic_id]:
                    oldest = min(
                        last_stats[statistic_id],
                        key=lambda x: x.get("start") if isinstance(x.get("start"), (int, float)) else (x.get("start").timestamp() if hasattr(x.get("start"), "timestamp") else 0),
                    )
                    o_sum = oldest.get("sum") or 0.0
                    o_state = oldest.get("state") or 0.0
                    base_sum = max(0.0, round(o_sum - o_state, 4))
        except Exception as ex:
            _LOGGER.debug("Could not query base statistics for %s: %s", statistic_id, ex)

        statistics: list[StatisticData] = []
        running_sum = base_sum
        for ts in all_utc_timestamps:
            kwh = daily_by_utc[ts]
            running_sum = round(running_sum + kwh, 4)
            statistics.append(
                StatisticData(
                    start=ts,
                    state=kwh,
                    sum=running_sum,
                )
            )

        meta_kwargs: dict = {
            "has_mean": False,
            "has_sum": True,
            "name": f"{self._name} Daily Energy (Official Daily Totals)",
            "source": DOMAIN,
            "statistic_id": statistic_id,
            "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        }
        if StatisticMeanType is not None:
            meta_kwargs["mean_type"] = StatisticMeanType.NONE
            meta_kwargs["unit_class"] = "energy"

        metadata = StatisticMetaData(**meta_kwargs)
        async_add_external_statistics(self.hass, metadata, statistics)

        # Import daily cost statistics
        effective_rate = self.get_effective_tariff_rate()
        statistic_cost_id = f"{DOMAIN}:{self._sensor_type}_daily_cost"
        base_cost_sum = 0.0
        try:
            last_cost_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 500, statistic_cost_id, True, {"sum", "state"}
            )
            if last_cost_stats and statistic_cost_id in last_cost_stats:
                found_c = False
                for stat in last_cost_stats[statistic_cost_id]:
                    s_time = stat.get("start")
                    rec_ts = float(s_time) if isinstance(s_time, (int, float)) else (s_time.timestamp() if hasattr(s_time, "timestamp") else None)
                    if rec_ts is not None and rec_ts < earliest_ts:
                        base_cost_sum = stat.get("sum") or 0.0
                        found_c = True
                        break
                if not found_c and last_cost_stats[statistic_cost_id]:
                    oldest_c = min(
                        last_cost_stats[statistic_cost_id],
                        key=lambda x: x.get("start") if isinstance(x.get("start"), (int, float)) else (x.get("start").timestamp() if hasattr(x.get("start"), "timestamp") else 0),
                    )
                    oc_sum = oldest_c.get("sum") or 0.0
                    oc_state = oldest_c.get("state") or 0.0
                    base_cost_sum = max(0.0, round(oc_sum - oc_state, 4))
        except Exception as ex:
            _LOGGER.debug("Could not query base cost statistics for %s: %s", statistic_cost_id, ex)

        cost_statistics: list[StatisticData] = []
        running_cost_sum = base_cost_sum
        for ts in all_utc_timestamps:
            kwh = daily_by_utc[ts]
            cost = round(kwh * effective_rate, 2)
            running_cost_sum = round(running_cost_sum + cost, 2)
            cost_statistics.append(
                StatisticData(
                    start=ts,
                    state=cost,
                    sum=running_cost_sum,
                )
            )

        meta_cost_kwargs: dict = {
            "has_mean": False,
            "has_sum": True,
            "name": f"{self._name} Daily Cost",
            "source": DOMAIN,
            "statistic_id": statistic_cost_id,
            "unit_of_measurement": "HKD",
        }
        if StatisticMeanType is not None:
            meta_cost_kwargs["mean_type"] = StatisticMeanType.NONE
            meta_cost_kwargs["unit_class"] = None

        metadata_cost = StatisticMetaData(**meta_cost_kwargs)
        async_add_external_statistics(self.hass, metadata_cost, cost_statistics)

    @handle_errors
    async def main_get_account_detail(self):
        response = await self.api_request(
            method="GET",
            url="https://api.clp.com.hk/ts1/ms/profile/accountdetails/myServicesCA",
            headers={
                "Authorization": self._access_token,
            },
        )
        active_accounts = [
            item for item in (response.get('data') or [])
            if str(item.get('status', '')).upper() == 'ACTIVE'
        ]
        if not active_accounts:
            active_accounts = response.get('data') or []

        if len(active_accounts) > 1 and not self._multi_account_warned:
            _LOGGER.warning(
                "%s: login has %d active CLP accounts; only the first is reported.",
                self._name, len(active_accounts),
            )
            self._multi_account_warned = True
        active_data = next(iter(active_accounts), None)
        ca_no = active_data.get('caNo') if active_data else None
        if not ca_no:
            self._account_number = None
            self._account = None
            if not self._no_account_warned:
                _LOGGER.warning("%s: no active CLP account with a usable account number; will keep retrying.", self._name)
                self._no_account_warned = True
            return

        self._account_number = ca_no
        self._account = {
            'number': ca_no,
            'outstanding': safe_float(active_data.get('outstandingAmount')),
            'due_date': parse_datetime(active_data.get('dueDate'), '%Y%m%d%H%M%S'),
        }
        self._no_account_warned = False
        self._account_last_fetch_time = datetime.datetime.now(self._timezone)
        self._single_task_last_fetch_time = self._account_last_fetch_time

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

        transactions = (response['data'] or {}).get('transactions') or []
        if transactions:
            bills = {
                'bill': [],
                'payment': [],
            }
            for row in transactions:
                row_type = row.get('type')
                if row_type not in ('bill', 'payment'):
                    continue

                record = {
                    'total': safe_float(row.get('total')),
                    'transaction_date': parse_datetime(row.get('tranDate'), '%Y%m%d%H%M%S'),
                }

                if row_type == 'bill':
                    record['from_date'] = parse_datetime(row.get('fromDate'), '%Y%m%d%H%M%S')
                    record['to_date'] = parse_datetime(row.get('toDate'), '%Y%m%d%H%M%S')

                bills[row_type].append(record)

            bills['bill'] = sorted(bills['bill'], key=lambda x: x['transaction_date'] or datetime.datetime.min, reverse=True)
            bills['payment'] = sorted(bills['payment'], key=lambda x: x['transaction_date'] or datetime.datetime.min, reverse=True)
            self._bills = bills
            self._bill_last_fetch_time = datetime.datetime.now(self._timezone)

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

        data = response['data']
        if data:
            self._estimation = {
                "current_consumption": safe_float(data.get('currentConsumption')),
                "current_cost": safe_float(data.get('currentCost')),
                "current_end_date": parse_datetime(data.get('currentEndDate'), '%Y%m%d%H%M%S'),
                "current_start_date": parse_datetime(data.get('currentStartDate'), '%Y%m%d%H%M%S'),
                "deviation_percent": safe_float(data.get('deviationPercent')),
                "estimation_consumption": safe_float(data.get('projectedConsumption')),
                "estimation_cost": safe_float(data.get('projectedCost')),
                "estimation_end_date": parse_datetime(data.get('projectedEndDate'), '%Y%m%d%H%M%S'),
                "estimation_start_date": parse_datetime(data.get('projectedStartDate'), '%Y%m%d%H%M%S'),
            }
            self._estimation_last_fetch_time = datetime.datetime.now(self._timezone)

    @handle_errors
    async def main_get_bimonthly(self):
        now = datetime.datetime.now(self._timezone)
        one_year_two_months_ago = now - relativedelta.relativedelta(years=1, months=2)

        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/consumption/history",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "ca": self._account_number,
                "fromDate": one_year_two_months_ago.strftime('%Y%m%d000000'),
                "mode": "Bill",
                "toDate": now.strftime('%Y%m%d000000'),
                "type": "Unit",
            },
        )

        if response['data']:
            results = response['data'].get('results') or []
            if results and self._type.upper() == 'BIMONTHLY':
                self._state_data_type = 'BIMONTHLY'
                self._attr_native_value = safe_float(results[0].get('totKwh'))
                self._last_reset = parse_datetime(results[0].get('endabrpe'), '%Y%m%d')

            if self._get_bimonthly:
                bimonthly = []
                for row in results:
                    bimonthly.append({
                        'end': parse_datetime(row.get('endabrpe'), '%Y%m%d'),
                        'kwh': safe_float(row.get('totKwh')),
                    })
                self._bimonthly = sorted(bimonthly, key=lambda x: x['end'] or datetime.datetime.min, reverse=True)
            self._bimonthly_last_fetch_time = datetime.datetime.now(self._timezone)

    @handle_errors
    async def main_get_daily(self):
        now = datetime.datetime.now(self._timezone)
        this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # CLP Daily API allows up to ~31 days per request.
        # Backfill 2 months on initial setup; subsequent 12h updates fetch current month only.
        months_to_fetch = 2 if not getattr(self, "_daily_backfill_done", False) else 1
        all_results: list[dict] = []
        for i in range(months_to_fetch - 1, -1, -1):
            m_start = this_month - relativedelta.relativedelta(months=i)
            m_end = this_month - relativedelta.relativedelta(months=i - 1)
            try:
                response = await self.api_request(
                    method="POST",
                    url="https://api.clp.com.hk/ts1/ms/consumption/history",
                    headers={
                        "Authorization": self._access_token,
                    },
                    json={
                        "ca": self._account_number,
                        "fromDate": m_start.strftime("%Y%m%d000000"),
                        "mode": "Daily",
                        "toDate": m_end.strftime("%Y%m%d000000"),
                        "type": "Unit",
                    },
                )
                if response and response.get('data'):
                    res = response['data'].get('results') or []
                    all_results.extend(res)
            except Exception as ex:
                _LOGGER.debug("Could not fetch daily records for %s: %s", m_start.strftime("%Y-%m"), ex)

        if all_results:
            self._daily_backfill_done = True
            results = all_results
            if results and self._type.upper() == 'DAILY':
                self._state_data_type = 'DAILY'
                self._attr_native_value = safe_float(results[-1].get('kwhTotal'))
                self._last_reset = parse_datetime(results[-1].get('expireDate'), '%Y%m%d%H%M%S')

            for row in results:
                start_str = str(row.get('startDate') or '')
                expire_str = str(row.get('expireDate') or '')
                kwh = safe_float(row.get('kwhTotal'))
                if len(start_str) >= 8 and expire_str.endswith('235959') and kwh is not None:
                    self._daily_totals[start_str[:8]] = kwh

            if self._get_daily:
                daily = []
                for row in results:
                    daily.append({
                        'start': parse_datetime(row.get('startDate'), '%Y%m%d%H%M%S'),
                        'end': parse_datetime(row.get('expireDate'), '%Y%m%d%H%M%S'),
                        'kwh': safe_float(row.get('kwhTotal')),
                    })
                self._daily = sorted(daily, key=lambda x: x['start'] or datetime.datetime.min, reverse=True)

            await self._import_daily_statistics(results)
            self._daily_last_fetch_time = datetime.datetime.now(self._timezone)

    @handle_errors
    async def main_get_hourly(self):
        if not getattr(self, "_daily_totals", None):
            await self.main_get_daily()

        hourly = []
        fetch_days = max(1, min(2, int(self._get_hourly_days or 2)))
        for i in range(1, fetch_days + 1):
            from_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(fetch_days - i))
            to_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(fetch_days - i - 1))

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

            results = (response['data'] or {}).get('results') or []
            if results:
                if i == fetch_days and (self._type == '' or self._type.upper() == 'HOURLY'):
                    self._state_data_type = 'HOURLY'
                    self._attr_native_value = safe_float(results[-1].get('kwhTotal'))
                    self._last_reset = parse_datetime(results[-1].get('expireDate'), '%Y%m%d%H%M%S')

                if self._get_hourly:
                    for row in results:
                        clp_dt = parse_datetime(row.get('startDate'), '%Y%m%d%H%M%S')
                        if clp_dt:
                            hour_start = clp_dt - datetime.timedelta(hours=1)
                            hourly.append({
                                'start': hour_start,
                                'kwh': safe_float(row.get('kwhTotal')),
                            })

                self._hourly_task_last_fetch_time = datetime.datetime.now(self._timezone)

        if self._get_hourly and hourly:
            self._hourly = sorted(hourly, key=lambda x: x['start'] or datetime.datetime.min, reverse=True)
            await self._import_hourly_statistics(hourly)

    @handle_errors
    async def renewable_get_bimonthly(self):
        now = datetime.datetime.now(self._timezone)
        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/renew/fit/dashboard",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "caNo": self._account_number,
                "mode": "B",
                "startDate": now.strftime("%m/%d/%Y"),
            },
        )

        consumption_data = (response.get('data') or {}).get('consumptionData') or []
        if consumption_data:
            if self._type.upper() == 'BIMONTHLY':
                self._state_data_type = 'BIMONTHLY'
                self._attr_native_value = safe_float(consumption_data[-1].get('kwhtotal'))
                self._last_reset = parse_datetime(consumption_data[-1].get('enddate'), '%Y%m%d%H%M%S')

            bills = []
            for row in consumption_data:
                bills.append({
                    'start': parse_datetime(row.get('startdate'), '%Y%m%d%H%M%S'),
                    'end': parse_datetime(row.get('enddate'), '%Y%m%d%H%M%S'),
                    'kwh': safe_float(row.get('kwhtotal')),
                })
            self._bills = sorted(bills, key=lambda x: x['start'] or datetime.datetime.min, reverse=True)
            self._bimonthly_last_fetch_time = datetime.datetime.now(self._timezone)

    @handle_errors
    async def renewable_get_daily(self):
        now = datetime.datetime.now(self._timezone)
        response = await self.api_request(
            method="POST",
            url="https://api.clp.com.hk/ts1/ms/renew/fit/dashboard",
            headers={
                "Authorization": self._access_token,
            },
            json={
                "caNo": self._account_number,
                "mode": "D",
                "startDate": now.strftime("%m/%d/%Y"),
            },
        )

        consumption_data = (response.get('data') or {}).get('consumptionData') or []
        if consumption_data:
            if self._type.upper() == 'DAILY':
                for row in sorted(consumption_data, key=lambda x: x.get('startdate') or '', reverse=True):
                    if row.get('validateStatus') == 'Y':
                        self._state_data_type = 'DAILY'
                        self._attr_native_value = safe_float(row.get('kwhtotal'))
                        self._last_reset = parse_datetime(row.get('startdate'), '%Y%m%d%H%M%S')
                        break

            daily = []
            for row in consumption_data:
                daily.append({
                    'start': parse_datetime(row.get('startdate'), '%Y%m%d%H%M%S'),
                    'kwh': safe_float(row.get('kwhtotal')),
                })
            self._daily = sorted(daily, key=lambda x: x['start'] or datetime.datetime.min, reverse=True)

            await self._import_daily_statistics(consumption_data)
            self._daily_last_fetch_time = datetime.datetime.now(self._timezone)

    @handle_errors
    async def renewable_get_hourly(self):
        hourly = []
        fetch_days = max(1, min(2, int(self._get_hourly_days or 2)))
        for i in range(1, fetch_days + 1):
            start_date = datetime.datetime.now(self._timezone) + datetime.timedelta(days=-(fetch_days - i))
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

            consumption_data = (response.get('data') or {}).get('consumptionData') or []
            if consumption_data:
                if i == fetch_days and (self._type == '' or self._type.upper() == 'HOURLY'):
                    for row in sorted(consumption_data, key=lambda x: x.get('startdate') or '', reverse=True):
                        if row.get('validateStatus') == 'Y':
                            self._state_data_type = 'HOURLY'
                            self._attr_native_value = safe_float(row.get('kwhtotal'))
                            self._last_reset = parse_datetime(row.get('startdate'), '%Y%m%d%H%M%S')
                            break

                for row in consumption_data:
                    if row.get('validateStatus') == 'N':
                        continue
                    hourly.append({
                        'start': parse_datetime(row.get('startdate'), '%Y%m%d%H%M%S'),
                        'kwh': safe_float(row.get('kwhtotal')),
                    })

                self._hourly_task_last_fetch_time = datetime.datetime.now(self._timezone)

        if hourly:
            self._hourly = sorted(hourly, key=lambda x: x['start'] or datetime.datetime.min, reverse=True)
            await self._import_hourly_statistics(hourly)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        _LOGGER.debug("[SENSOR UPDATE] Starting update for %s", self._name)
        self._error = None
        try:
            await self._fetch_all()
        except FatalAuthError as e:
            self._error = str(e)
            self._fatal_error = True
            _LOGGER.error("%s: fatal auth error; integration stopped.", self._name)

    async def _fetch_all(self) -> None:
        if not self._access_token:
            _LOGGER.debug("[SENSOR UPDATE] No access token, skipping data fetch.")
            return

        if self._sensor_type == 'main':
            now = datetime.datetime.now(self._timezone)
            if not self._tariff_last_fetch_time or (now.year, now.month) != self._latest_tariff.get("year_month"):
                await self.async_fetch_monthly_tariff()

            if not self._account_last_fetch_time or not self._account_number:
                if not self._account_number or self._get_acct:
                    _LOGGER.debug("[SENSOR UPDATE] Fetching account detail.")
                    await self.main_get_account_detail()

            if not self._account_number:
                _LOGGER.debug("%s: no account number; skipping data fetch this cycle.", self._name)
                return

            if self._get_bill and (
                not self._bill_last_fetch_time or now > self._bill_last_fetch_time + DAILY_TASK_INTERVAL
            ):
                _LOGGER.debug("[SENSOR UPDATE] Fetching bill.")
                await self.main_get_bill()

            if self._get_estimation and (
                not self._estimation_last_fetch_time or now > self._estimation_last_fetch_time + DAILY_TASK_INTERVAL
            ):
                _LOGGER.debug("[SENSOR UPDATE] Fetching estimation.")
                await self.main_get_estimation()

            if (self._get_bimonthly or self._type.upper() == 'BIMONTHLY') and (
                not self._bimonthly_last_fetch_time or now > self._bimonthly_last_fetch_time + DAILY_TASK_INTERVAL
            ):
                _LOGGER.debug("[SENSOR UPDATE] Fetching bimonthly.")
                await self.main_get_bimonthly()

            if (self._get_daily or self._type.upper() == 'DAILY') and (
                not self._daily_last_fetch_time or now > self._daily_last_fetch_time + DAILY_TASK_INTERVAL
            ):
                _LOGGER.debug("[SENSOR UPDATE] Fetching daily.")
                await self.main_get_daily()

            if (self._get_hourly or self._type == '' or self._type.upper() == 'HOURLY') and (
                not self._hourly_last_fetch_time or now > self._hourly_last_fetch_time + HOURLY_TASK_INTERVAL
            ):
                _LOGGER.debug("[SENSOR UPDATE] Fetching hourly.")
                await self.main_get_hourly()

        elif self._sensor_type == 'renewable_energy':
            now = datetime.datetime.now(self._timezone)
            if not self._account_last_fetch_time or not self._account_number:
                _LOGGER.debug("[SENSOR UPDATE] Fetching renewable account detail.")
                await self.main_get_account_detail()

            if not self._account_number:
                _LOGGER.debug("%s: no account number; skipping renewable data fetch.", self._name)
                return

            if not self._bimonthly_last_fetch_time or now > self._bimonthly_last_fetch_time + DAILY_TASK_INTERVAL:
                _LOGGER.debug("[SENSOR UPDATE] Fetching renewable bimonthly.")
                await self.renewable_get_bimonthly()

            if not self._daily_last_fetch_time or now > self._daily_last_fetch_time + DAILY_TASK_INTERVAL:
                _LOGGER.debug("[SENSOR UPDATE] Fetching renewable daily.")
                await self.renewable_get_daily()

            if not self._hourly_last_fetch_time or now > self._hourly_last_fetch_time + HOURLY_TASK_INTERVAL:
                _LOGGER.debug("[SENSOR UPDATE] Fetching renewable hourly.")
                await self.renewable_get_hourly()

        if self._type == '' and self._state_data_type is not None:
            self._type = self._state_data_type

        for sub in getattr(self, "_sub_sensors", []):
            if getattr(sub, "hass", None):
                sub.async_write_ha_state()


class CLPSubSensor(SensorEntity):
    """Sub-sensor for specific CLP metric (e.g. projected cost, base tariff rate)."""

    def __init__(
        self,
        parent: CLPSensor,
        sub_key: str,
        name: str,
        device_class: SensorDeviceClass | None,
        unit_of_measurement: str | None,
        state_class: SensorStateClass | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        self._parent = parent
        self._sub_key = sub_key
        self._attr_name = name
        if sub_key == "tariff_rate":
            self._attr_suggested_object_id = "clp_projected_effective_tariff_rate"
        else:
            self._attr_suggested_object_id = f"clp_{sub_key}"
        self._attr_unique_id = f"clphk_{parent.sensor_type}_{sub_key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        self._attr_should_poll = False

    @property
    def device_info(self) -> DeviceInfo:
        return self._parent.device_info

    @property
    def icon(self) -> str | None:
        if self._sub_key == "tier_consumption":
            return "mdi:chart-box-outline"
        elif self._sub_key == "tier_rates":
            return "mdi:format-list-numbered"
        elif self._sub_key in ("base_tariff", "tariff_rate"):
            return "mdi:cash-multiple"
        elif self._sub_key == "fuel_adjustment":
            return "mdi:gas-burner"
        return None

    @property
    def native_value(self):
        est = self._parent.estimation or {}
        bills = self._parent.bills or {}
        acct = self._parent.account or {}

        if self._sub_key == "projected_cost":
            return est.get("estimation_cost")
        elif self._sub_key == "current_consumption":
            return est.get("current_consumption")
        elif self._sub_key == "projected_consumption":
            return est.get("estimation_consumption")
        elif self._sub_key == "last_bill":
            bill_list = bills.get("bill") or []
            return bill_list[0].get("total") if bill_list else None
        elif self._sub_key == "outstanding":
            return acct.get("outstanding")
        elif self._sub_key == "base_tariff":
            tier_rates = self._parent.get_effective_tier_rates()
            return round(float(tier_rates[0]), 4) if tier_rates else 0.945
        elif self._sub_key == "fuel_adjustment":
            if self._parent.custom_fuel_cents is not None and self._parent.custom_fuel_cents > 0:
                return round(self._parent.custom_fuel_cents / 100.0, 4)
            tariff = self._parent.latest_tariff or {}
            fuel_cents = tariff.get("fuel_cents", 47.4)
            return round(fuel_cents / 100.0, 4)
        elif self._sub_key == "tariff_rate":
            return self._parent.get_effective_tariff_rate()
        elif self._sub_key == "tier_consumption":
            curr_kwh = safe_float(est.get("current_consumption"))
            if curr_kwh is None:
                curr_kwh = safe_float(est.get("estimation_consumption"))
            tier_limits = self._parent.get_effective_tier_limits()
            tier_rates = self._parent.get_effective_tier_rates()
            dist = calculate_tier_consumption(curr_kwh or 0.0, tier_limits, len(tier_rates))
            return f"Tier {dist['current_tier']}"
        elif self._sub_key == "tier_rates":
            curr_kwh = safe_float(est.get("current_consumption"))
            if curr_kwh is None:
                curr_kwh = safe_float(est.get("estimation_consumption"))
            tier_limits = self._parent.get_effective_tier_limits()
            tier_rates = self._parent.get_effective_tier_rates()
            dist = calculate_tier_consumption(curr_kwh or 0.0, tier_limits, len(tier_rates))
            curr_tier = dist["current_tier"]
            return round(float(tier_rates[curr_tier - 1]), 4) if tier_rates else 0.945
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._sub_key == "tariff_rate":
            tariff = self._parent.latest_tariff or {}
            mode = "auto"
            if self._parent.custom_fixed_rate and self._parent.custom_fixed_rate > 0:
                mode = "custom_fixed"
            elif self._parent.custom_rate_entity:
                mode = f"entity:{self._parent.custom_rate_entity}"
            elif self._parent.custom_fuel_cents and self._parent.custom_fuel_cents > 0:
                mode = "custom_fuel"
            elif self._parent.custom_tier_rates or self._parent.custom_tier_limits:
                mode = "custom_tiers"

            fuel_cents = self._parent.custom_fuel_cents if (self._parent.custom_fuel_cents and self._parent.custom_fuel_cents > 0) else tariff.get("fuel_cents", 47.4)
            ym = tariff.get("year_month")
            tariff_period = f"{ym[0]}-{ym[1]:02d}" if isinstance(ym, (tuple, list)) and len(ym) >= 2 else None
            tier_rates = self._parent.get_effective_tier_rates()
            tier_limits = self._parent.get_effective_tier_limits()
            return {
                "tariff_mode": mode,
                "base_tariff_rate_hkd": round(float(tier_rates[0]), 4) if tier_rates else 0.945,
                "tier_rates_hkd": tier_rates,
                "tier_limits_kwh": tier_limits,
                "fuel_clause_adjustment_cents": fuel_cents,
                "fuel_clause_adjustment_hkd": round(fuel_cents / 100.0, 4),
                "special_fuel_rebate_cents": tariff.get("special_fuel_rebate_cents", 0.0),
                "energy_saving_rebate_hkd": round(float(tariff.get("rebate", 0.172)), 4),
                "subsidy_hkd": self._parent.custom_subsidy or 0.0,
                "tariff_period": tariff_period,
                "calculation_basis": "Projected Effective Rate = Estimated Total Cost / Estimated Total Consumption",
                "last_tariff_synced": tariff.get("last_synced"),
            }
        elif self._sub_key == "base_tariff":
            tariff = self._parent.latest_tariff or {}
            ym = tariff.get("year_month")
            tariff_period = f"{ym[0]}-{ym[1]:02d}" if isinstance(ym, (tuple, list)) and len(ym) >= 2 else None
            est = self._parent.estimation or {}
            curr_kwh = est.get("current_consumption") or est.get("estimation_consumption") or 0.0

            tier_rates = self._parent.get_effective_tier_rates()
            tier_limits = self._parent.get_effective_tier_limits()

            tier = 1
            accum = 0.0
            for idx, limit in enumerate(tier_limits):
                accum += limit
                if curr_kwh > accum:
                    tier = idx + 2
                else:
                    break
            tier = min(tier, len(tier_rates)) if tier_rates else 1
            current_tier_rate = tier_rates[tier - 1] if tier_rates else 0.945

            tier_1_limit_desc = f"first {int(tier_limits[0])} kWh" if tier_limits else "all consumption"
            attrs = {
                "description": f"Base tariff rate for tier 1 ({tier_1_limit_desc}). See current_tier_rate for rate based on consumption.",
                "unit": "HKD/kWh",
                "total_tiers": len(tier_rates),
                "current_tier": tier,
                "current_tier_rate": current_tier_rate,
                "tier_rates_hkd": tier_rates,
                "tier_limits_kwh": tier_limits,
                "is_custom_tier_override": bool(self._parent.custom_tier_rates or self._parent.custom_tier_limits),
                "tariff_period": tariff_period,
                "last_tariff_synced": tariff.get("last_synced"),
            }
            for idx, limit in enumerate(tier_limits):
                attrs[f"tier_{idx+1}_limit_kwh"] = limit
                if idx < len(tier_rates):
                    attrs[f"tier_{idx+1}_rate_hkd"] = tier_rates[idx]
            if tier_rates:
                last_idx = len(tier_rates)
                attrs[f"tier_{last_idx}_rate_hkd"] = tier_rates[-1]
                if tier_limits:
                    attrs[f"tier_{last_idx}_limit_kwh"] = f"> {int(sum(tier_limits))}"
                else:
                    attrs[f"tier_{last_idx}_limit_kwh"] = "all"
            return attrs
        elif self._sub_key == "fuel_adjustment":
            tariff = self._parent.latest_tariff or {}
            ym = tariff.get("year_month")
            tariff_period = f"{ym[0]}-{ym[1]:02d}" if isinstance(ym, (tuple, list)) and len(ym) >= 2 else None
            return {
                "is_custom_override": bool(self._parent.custom_fuel_cents and self._parent.custom_fuel_cents > 0),
                "special_fuel_rebate_cents": tariff.get("special_fuel_rebate_cents", 0.0),
                "tariff_period": tariff_period,
                "last_tariff_synced": tariff.get("last_synced"),
            }
        elif self._sub_key == "tier_consumption":
            est = self._parent.estimation or {}
            curr_kwh = safe_float(est.get("current_consumption")) or 0.0
            proj_kwh = safe_float(est.get("estimation_consumption")) or 0.0
            tier_rates = self._parent.get_effective_tier_rates()
            tier_limits = self._parent.get_effective_tier_limits()
            n_tiers = len(tier_rates)

            actual_dist = calculate_tier_consumption(curr_kwh, tier_limits, n_tiers)
            proj_dist = calculate_tier_consumption(proj_kwh, tier_limits, n_tiers)

            curr_tier = actual_dist["current_tier"]
            tier_used = actual_dist["tier_used"]
            tier_remaining = actual_dist["tier_remaining"]

            attrs = {
                "current_tier": curr_tier,
                "total_tiers": n_tiers,
                "current_consumption_kwh": round(curr_kwh, 2),
                "projected_consumption_kwh": round(proj_kwh, 2),
                "projected_tier": proj_dist["current_tier"],
                "current_tier_used_kwh": tier_used[curr_tier - 1] if curr_tier <= len(tier_used) else 0.0,
            }
            if curr_tier <= len(tier_limits):
                attrs["current_tier_limit_kwh"] = tier_limits[curr_tier - 1]
                attrs["current_tier_remaining_kwh"] = tier_remaining[curr_tier - 1] if curr_tier <= len(tier_remaining) else 0.0
            else:
                attrs["current_tier_limit_kwh"] = f"> {int(sum(tier_limits))}" if tier_limits else "all"
                attrs["current_tier_remaining_kwh"] = "unbounded"

            breakdown = {}
            proj_breakdown = {}
            for i in range(n_tiers):
                t_idx = i + 1
                used = tier_used[i] if i < len(tier_used) else 0.0
                attrs[f"tier_{t_idx}_used_kwh"] = used
                breakdown[f"tier_{t_idx}"] = used

                p_used = proj_dist["tier_used"][i] if i < len(proj_dist["tier_used"]) else 0.0
                attrs[f"projected_tier_{t_idx}_used_kwh"] = p_used
                proj_breakdown[f"tier_{t_idx}"] = p_used

                if i < len(tier_limits):
                    attrs[f"tier_{t_idx}_limit_kwh"] = tier_limits[i]
                    attrs[f"tier_{t_idx}_remaining_kwh"] = tier_remaining[i] if i < len(tier_remaining) else 0.0
                else:
                    attrs[f"tier_{t_idx}_limit_kwh"] = f"> {int(sum(tier_limits))}" if tier_limits else "all"
                    attrs[f"tier_{t_idx}_remaining_kwh"] = "unbounded"

            attrs["tier_consumption_breakdown"] = breakdown
            attrs["projected_tier_breakdown"] = proj_breakdown
            return attrs
        elif self._sub_key == "tier_rates":
            tariff = self._parent.latest_tariff or {}
            ym = tariff.get("year_month")
            tariff_period = f"{ym[0]}-{ym[1]:02d}" if isinstance(ym, (tuple, list)) and len(ym) >= 2 else None
            est = self._parent.estimation or {}
            curr_kwh = safe_float(est.get("current_consumption")) or 0.0
            tier_rates = self._parent.get_effective_tier_rates()
            tier_limits = self._parent.get_effective_tier_limits()
            n_tiers = len(tier_rates)

            dist = calculate_tier_consumption(curr_kwh, tier_limits, n_tiers)
            curr_tier = dist["current_tier"]
            current_tier_rate = round(float(tier_rates[curr_tier - 1]), 4) if tier_rates else 0.945

            attrs = {
                "current_tier": curr_tier,
                "current_tier_rate_hkd": current_tier_rate,
                "total_tiers": n_tiers,
                "tier_rates_hkd": tier_rates,
                "tier_limits_kwh": tier_limits,
                "is_custom_tier_override": bool(self._parent.custom_tier_rates or self._parent.custom_tier_limits),
                "tariff_period": tariff_period,
                "last_tariff_synced": tariff.get("last_synced"),
            }
            rates_breakdown = {}
            for i, rate in enumerate(tier_rates):
                t_idx = i + 1
                attrs[f"tier_{t_idx}_rate_hkd"] = rate
                rates_breakdown[f"tier_{t_idx}"] = rate
                if i < len(tier_limits):
                    attrs[f"tier_{t_idx}_limit_kwh"] = tier_limits[i]
                else:
                    attrs[f"tier_{t_idx}_limit_kwh"] = f"> {int(sum(tier_limits))}" if tier_limits else "all"

            attrs["tier_rates_breakdown"] = rates_breakdown
            return attrs
        return {}

    @property
    def available(self) -> bool:
        return self._parent.available

    async def async_added_to_hass(self) -> None:
        self._parent.register_sub_sensor(self)

    async def async_will_remove_from_hass(self) -> None:
        self._parent.unregister_sub_sensor(self)
