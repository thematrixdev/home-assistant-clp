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

