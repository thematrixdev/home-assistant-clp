from __future__ import annotations

import base64
import datetime
import json
import re

CONF_DOMAIN = 'clphk'

# HTTP status / CLP error-code classification for token handling.
# Only genuine auth failures clear stored tokens; transient statuses never do.
AUTH_FAILURE_STATUSES = (401, 403)
TRANSIENT_STATUSES = (408, 429)
TOKEN_EXPIRED_CODES = (906, 100001)  # 906: access token expired; 100001: LR access_token error

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


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


def parse_combined_tokens(raw_text: str) -> tuple[str | None, str | None]:
    if not raw_text or not raw_text.strip():
        return None, None
    text = raw_text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            act = parsed.get("act") or parsed.get("access_token") or parsed.get("accessToken")
            rct = parsed.get("rct") or parsed.get("refresh_token") or parsed.get("refreshToken")
            if act and rct:
                return str(act).strip(), str(rct).strip()
    except Exception:
        pass

    act_match = re.search(r'(?:access[_\s-]*token|act)[\s:=]+({[^{}]*}|"[^"]+"|[A-Za-z0-9+/=_-]{30,})', text, re.IGNORECASE)
    rct_match = re.search(r'(?:refresh[_\s-]*token|rct)[\s:=]+({[^{}]*}|"[^"]+"|[A-Za-z0-9+/=_-]{30,})', text, re.IGNORECASE)
    if act_match and rct_match:
        return act_match.group(1).strip(), rct_match.group(1).strip()

    json_objs = re.findall(r'\{[^{}]*"data"[^{}]*\}', text)
    if len(json_objs) >= 2:
        return json_objs[0].strip(), json_objs[1].strip()

    candidates = []
    for line in text.splitlines():
        token = _extract_allowed_b64_token(line)
        if token:
            candidates.append(token)
    if len(candidates) >= 2:
        return candidates[0], candidates[1]

    return None, None


def is_auth_failure(status, error_code):
    """True when a 4xx response means the credentials are unusable (wipe + stop).

    A bare 401/403 is auth denial. TOKEN_EXPIRED_CODES only reach the wipe path
    after a refresh has already been attempted (or when no refresh token exists),
    i.e. the token is dead and cannot be recovered.
    """
    return status in AUTH_FAILURE_STATUSES or error_code in TOKEN_EXPIRED_CODES


def is_transient(status):
    """True for 4xx statuses that are temporary and must not clear tokens."""
    return status in TRANSIENT_STATUSES


def parse_refresh_tokens(response_json):
    """Extract (access_token, refresh_token, expires_in) from a refresh response.

    Returns None when the body is unusable (not a dict, no "data" dict, or the
    access/refresh token is missing/empty). A well-formed refresh that lacks a
    token is unrecoverable, so the caller treats None as a fatal auth failure
    rather than retrying with a possibly-consumed refresh token. expires_in is
    optional (not used for control flow) and returned as-is, defaulting to None.
    """
    if not isinstance(response_json, dict):
        return None
    data = response_json.get("data")
    if not isinstance(data, dict):
        return None
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not access or not refresh:
        return None
    return access, refresh, data.get("expires_in")


def safe_float(value):
    """float(value), or None when value is null/empty/non-numeric.

    CLP returns null for fields like a projection that does not exist yet or an
    account with no current bill; float(None) would raise. None keeps the sensor
    value/attribute as 'unknown' instead of crashing the whole update.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value, fmt):
    """strptime(value, fmt), or None when value is null/empty/unparseable."""
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, fmt)
    except (TypeError, ValueError):
        return None


def calculate_residential_bill(
    kwh: float,
    days: int = 60,
    fuel_cents: float = 39.4,
    special_fuel_rebate_cents: float = 0.0,
    subsidy: float = 0.0,
    custom_fixed_rate: float | None = None,
) -> dict:
    """Calculate CLP residential electricity bill amount based on official tariff table.

    Tiers (scaled by days/60 when days not in 55..65):
    - First 400 kWh: 94.5 cents/kWh
    - Next 600 kWh: 107.9 cents/kWh
    - Next 800 kWh: 123.7 cents/kWh
    - Next 800 kWh: 154.5 cents/kWh
    - Next 800 kWh: 177.4 cents/kWh
    - Next 800 kWh: 187.8 cents/kWh
    - Above 4200 kWh: 189.0 cents/kWh

    Fuel Clause Adjustment: fuel_cents / kWh
    Special Fuel Rebate: special_fuel_rebate_cents / kWh
    Energy Saving Rebate (when bi-monthly total <= 400 kWh):
    - 1..200 kWh: 17.2 cents/kWh
    - 201..300 kWh: 16.2 cents/kWh
    - 301..400 kWh: 15.2 cents/kWh
    Minimum charge: HK$40
    Subsidy: deducted from total bill in HKD
    Custom Fixed Rate: if specified (>0), uses fixed rate (HKD/kWh)
    """
    if custom_fixed_rate is not None and custom_fixed_rate > 0:
        net_dollars = round(max(0.0, kwh * custom_fixed_rate - subsidy), 2)
        return {
            "basic_tariff": 0.0,
            "fuel_charge": 0.0,
            "rebate": 0.0,
            "special_rebate": 0.0,
            "subsidy": round(subsidy, 2),
            "total": net_dollars,
            "effective_rate": round(custom_fixed_rate, 4),
        }

    scale = (days / 60.0) if (days < 55 or days > 65) else 1.0
    tier_limits = [400 * scale, 600 * scale, 800 * scale, 800 * scale, 800 * scale, 800 * scale]
    tier_rates = [94.5, 107.9, 123.7, 154.5, 177.4, 187.8, 189.0]

    remaining = max(0.0, float(kwh))
    basic_tariff_cents = 0.0
    for limit, rate in zip(tier_limits, tier_rates):
        take = min(remaining, limit)
        basic_tariff_cents += take * rate
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0:
        basic_tariff_cents += remaining * tier_rates[-1]

    fuel_cents_total = max(0.0, float(kwh)) * fuel_cents
    special_rebate_cents_total = max(0.0, float(kwh)) * special_fuel_rebate_cents

    rebate_cents = 0.0
    rebate_limit = 400 * scale
    if kwh <= rebate_limit:
        if kwh <= 200 * scale:
            rebate_cents = kwh * 17.2
        elif kwh <= 300 * scale:
            rebate_cents = kwh * 16.2
        else:
            rebate_cents = kwh * 15.2

    net_cents = basic_tariff_cents + fuel_cents_total - rebate_cents - special_rebate_cents_total
    gross_dollars = net_cents / 100.0
    net_dollars = round(max(40.0, gross_dollars - subsidy), 2)
    return {
        "basic_tariff": round(basic_tariff_cents / 100.0, 2),
        "fuel_charge": round(fuel_cents_total / 100.0, 2),
        "rebate": round(rebate_cents / 100.0, 2),
        "special_rebate": round(special_rebate_cents_total / 100.0, 2),
        "subsidy": round(subsidy, 2),
        "total": net_dollars,
        "effective_rate": round(net_dollars / max(1.0, kwh), 4),
    }

CONF_GET_ACCT = 'get_account'
CONF_GET_BILL = 'get_bill'
CONF_GET_ESTIMATION = 'get_estimation'
CONF_GET_BIMONTHLY = 'get_bimonthly'
CONF_GET_DAILY = 'get_daily'
CONF_GET_HOURLY = 'get_hourly'
CONF_GET_HOURLY_DAYS = 'get_hourly_days'

CONF_RES_ENABLE = 'renewable_energy_sensor_enable'
CONF_RES_NAME = 'renewable_energy_sensor_name'
CONF_RES_TYPE = 'renewable_energy_sensor_type'
CONF_RES_GET_BILL = 'renewable_energy_sensor_get_bill'
CONF_RES_GET_DAILY = 'renewable_energy_sensor_get_daily'
CONF_RES_GET_HOURLY = 'renewable_energy_sensor_get_hourly'
CONF_RES_GET_HOURLY_DAYS = 'renewable_energy_sensor_get_hourly_days'

CONF_COMBINED_TOKENS = 'combined_tokens'

CONF_CUSTOM_FUEL_CENTS = 'custom_fuel_cents'
CONF_CUSTOM_FIXED_RATE = 'custom_fixed_rate'
CONF_CUSTOM_SUBSIDY = 'custom_subsidy'
CONF_CUSTOM_RATE_ENTITY = 'custom_rate_entity'

