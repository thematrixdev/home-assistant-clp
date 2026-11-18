# CLP (HK) Statistic Home-Assistant Custom-Component

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

Seamlessly sync electricity bills, current cycle estimations, progressive tiered rates, and hourly smart meter readings from China Light & Power (CLP Hong Kong) directly into Home Assistant and the official **Energy Dashboard**.

---

## 🌟 Key Features

* **⚡ Native Home Assistant Energy Dashboard Integration**: Direct integration with Home Assistant Long-Term Statistics (`async_add_external_statistics`), solving the natural 3-hour CLP data delay by strictly mapping hourly consumption to exact historical timestamps.
* **📊 Official Tiered Tariff Auto-Fetch**: Automatically retrieves the latest official residential energy charge tiers, monthly fuel clause adjustment, and special rebates from CLP’s official billing calculator API.
* **🔄 Adaptive N-Tier Pricing & Customization**:
  * Adapts dynamically to any number of tiers $N$ (e.g. flat rate, 3 tiers, 5 tiers, or CLP standard 7 tiers).
  * Built-in harmonization algorithm (`reconcile_tariff_tiers`) that aligns rates and tier thresholds smoothly, with full tolerance for both English (`,`) and Chinese full-width (`，`) commas.
  * Supports fixed pricing overrides, manual fuel clause locking, bi-monthly government subsidy deduction, or external dynamic rate entities.
* **🔍 Dedicated Diagnostic Entities**:
  * **Tier Consumption (`sensor.clp_tier_consumption`)**: Reports active tier level, with attributes breaking down exact kWh consumed per tier, remaining tier allowances, and projected cycle distributions.
  * **Tier Rates (`sensor.clp_tier_rates`)**: Reports current active unit price, with attributes detailing complete tier pricing schedules and block thresholds.
* **🌱 Renewable Energy (Feed-in Tariff / FiT)**: Full support for residential and business solar/wind FiT accounts, tracking energy generation and feed-in tariff billing revenues.
* **💰 Official Energy Saving Rebate**: Accurately simulates CLP’s official bi-monthly consumption rebate for bills up to 400 kWh (17.2¢/kWh for 1-200 kWh, 16.2¢/kWh for 201-300 kWh, 15.2¢/kWh for 301-400 kWh).
* **🛡️ Automatic Token Refresh & Native Re-authentication**: Seamless background token rotation, plus native HA "Reconfigure" cards if login credentials ever expire.
* **⏱️ Decoupled Polling Intervals**: Throttles hourly (60m), daily (12h), and estimation/billing (5m) sync cycles to ensure reliable performance without triggering CLP rate limits.

---

## Table of Contents

- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Add to HACS](#add-to-hacs)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
  - [Configuration Flow](#configuration-flow)
  - [Obtaining CLP Tokens](#obtaining-clp-tokens)
  - [One-Click Paste & Token Formats](#one-click-paste--token-formats)
- [Energy Dashboard Integration](#energy-dashboard-integration)
- [Entities and Sensors List](#entities-and-sensors-list)
  - [Standard Sensors](#standard-sensors)
  - [Diagnostic Entities](#diagnostic-entities)
- [Configuration Parameters](#configuration-parameters)
- [Tiered Pricing & Billing Semantics](#tiered-pricing--billing-semantics)
- [Re-authentication & Re-login](#re-authentication--re-login)
- [Troubleshooting & Debugging](#troubleshooting--debugging)

---

## Installation

### Prerequisites

- CLP Hong Kong subscriber
- CLP online account credentials
- CLP smart meter installed (for `HOURLY` data)

### Add to HACS

1. Ensure [HACS](https://hacs.xyz/docs/setup/prerequisites) is installed.
2. In Home Assistant, click **HACS** on the left menu ➔ **Integrations**.
3. Click the top-right menu icon (three dots) ➔ **Custom repositories**.
4. Enter `https://github.com/thematrixdev/home-assistant-clp`, select `Integration`, and click **Add**.
5. Find **CLPHK** in the list and click **Download**.
6. Restart Home Assistant.

### Manual Installation

1. Download this repository.
2. Copy `custom_components/clphk` into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

### Configuration Flow

1. Go to **Settings** ➔ **Devices & Services** ➔ **Add Integration**.
2. Search and select **CLPHK**.
3. **Step 1 (Guide)**: Read the token retrieval instructions and click **Next**.
4. **Step 2 (Tokens)**: Paste the copied output directly into **Paste All Tokens (One-Click)**.
5. **Step 3 (Options)**: Configure device name, tariff options, and sync preferences.

---

### Obtaining CLP Tokens

1. Open an **Incognito window** in Chrome or Edge (`Ctrl+Shift+N` or `Cmd+Shift+N`).
2. Navigate to [CLP Online Login](https://www.clp.com.hk/services/en/login) and sign in.
3. Press **F12** (or right-click anywhere and click **Inspect**) to open DevTools.
4. Go to the **Console** tab, paste and press Enter:
   ```javascript
   console.log("Access Token:\n" + localStorage.getItem("act") + "\n\nRefresh Token:\n" + localStorage.getItem("rct"));
   ```
5. Copy the entire printed text output.
6. **Close the Incognito window directly** (**DO NOT click "Sign Out"**).
7. Return to Home Assistant and paste the text into the **"Paste All Tokens (One-Click)"** box.

> ⚠️ **CRITICAL WARNING**: **Never click "Sign Out"** on the CLP website. Signing out immediately revokes your Refresh Token on CLP servers. Simply close the browser window or tab.

*(Alternative manual method: copy `act` and `rct` from DevTools `Application` ➔ `Storage` ➔ `Local Storage` ➔ `https://www.clp.com.hk`)*

---

### One-Click Paste & Token Formats

The setup dialog automatically recognizes and parses:
- Console outputs with `Access Token:` and `Refresh Token:` labels
- Single JSON object containing `act`/`rct` or `access_token`/`refresh_token`
- Separate JSON objects `{"data":"...","time":...,"expire":"..."}`
- Plain Base64 token strings

---

## Energy Dashboard Integration

Because CLP electricity data is naturally delayed by ~3 hours, importing readings at collection time causes hourly graphs to shift by 3 hours. 

This integration automatically backfills **Home Assistant Long-Term Statistics** (`clphk:main_hourly_energy`, named `CLP Hourly Energy`) with exact historical hourly timestamps directly from CLP:
1. Go to **Settings** -> **Dashboards** -> **Energy**.
2. Under **Electricity Grid**, click **Add Consumption**.
3. Choose statistic **CLP Hourly Energy** (`clphk:main_hourly_energy`).
4. For tracking costs, choose **Use an entity tracking the total costs or price** and select **Projected Effective Tariff Rate** (`sensor.clp_projected_effective_tariff_rate`).
5. Your hourly grid consumption will align accurately with true historical usage!

---

## Entities and Sensors List

### Standard Sensors
| Entity ID (Suggested/Default) | Entity Name | Unit | Description |
| :--- | :--- | :---: | :--- |
| `sensor.clp` | Main Meter Sensor | `kWh` | Primary reading entity (configurable for hourly, daily, or bi-monthly state) |
| `sensor.clp_projected_cost` | Projected Cost | `HKD` | Projected total electricity cost for the current billing period |
| `sensor.clp_current_period_consumption` | Current Period Consumption | `kWh` | Actual cumulative energy consumed so far in the active billing period |
| `sensor.clp_projected_consumption` | Projected Consumption | `kWh` | Projected total energy consumption for the billing period |
| `sensor.clp_last_bill_amount` | Last Bill Amount | `HKD` | Total payable amount on the most recently issued bill |
| `sensor.clp_outstanding_amount` | Outstanding Amount | `HKD` | Unsettled account balance / overdue amount |
| `sensor.clp_base_tariff_rate` | Base Tariff Rate | `HKD/kWh` | Base energy charge for tier 1 (attributes contain full tier schedule) |
| `sensor.clp_fuel_clause_adjustment` | Fuel Clause Adjustment | `HKD/kWh` | Current monthly fuel clause adjustment published by CLP |
| `sensor.clp_projected_effective_tariff_rate` | Projected Effective Tariff Rate | `HKD/kWh` | **Projected effective comprehensive rate** (Projected Cost / Projected Consumption) |

### Diagnostic Entities
Located in the "Diagnostic" category on the Home Assistant device page:
| Entity ID | Entity Name | State | Key Attributes |
| :--- | :--- | :---: | :--- |
| `sensor.clp_tier_consumption` | Tier Consumption | `Tier X` (e.g. `Tier 1`) | **Tier consumption breakdown**: `current_tier_used_kwh`, `current_tier_remaining_kwh`, individual `tier_1_used_kwh` ~ `tier_N_used_kwh`, `tier_consumption_breakdown` dict, and `projected_tier_breakdown` |
| `sensor.clp_tier_rates` | Tier Rates | Active rate (e.g. `0.945`) | **Tier pricing schedule**: `current_tier_rate_hkd`, `tier_1_rate_hkd` ~ `tier_N_rate_hkd`, limits `tier_1_limit_kwh` ~ `tier_N_limit_kwh`, and `tier_rates_breakdown` dict |

---

## Configuration Parameters

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `combined_tokens` | string | ` ` | One-click paste field for full token console output |
| `access_token` | string | ` ` | CLP Access Token (leave blank if pasted above) |
| `refresh_token` | string | ` ` | CLP Refresh Token (leave blank if pasted above) |
| `name` | string | `CLP` | Integration/device prefix name |
| `timeout` | int | `30` | API connection timeout in seconds |
| `custom_fixed_rate` | float | `0.0` | **Custom Fixed Price (HKD/kWh)**: Default 0 uses official tiered calculation; positive value enforces a flat rate. |
| `custom_fuel_cents` | float | `0.0` | **Custom Fuel Clause (cents/kWh)**: Default 0 auto-syncs official rate; positive value locks the rate manually. |
| `custom_subsidy` | float | `0.0` | **Bi-monthly Subsidy / Rebate (HKD)**: Government electricity subsidy deduction per bi-monthly bill. |
| `custom_rate_entity` | string | ` ` | **Dynamic Tariff Entity ID**: Optional entity (e.g. `input_number.clp_rate`) to dynamically control tariff rate. |
| `custom_tier_rates` | string | ` ` | **Custom Tier Rates (HKD/kWh)**: Comma-separated unit prices (e.g. `0.945, 1.079, 1.237...` or `1.0, 1.5, 2.0`), adapting to arbitrary tier counts. |
| `custom_tier_limits` | string | ` ` | **Custom Tier Limits (kWh)**: Comma-separated limits for tiers 1 to N-1 (e.g. `400, 600, 800...` or `200, 300`). Final tier is automatically unbounded. |
| `get_hourly` | boolean | `True` | Sync hourly usage (required for Energy Dashboard) |
| `get_hourly_days` | int | `2` | History days to query for hourly data (recommend 2 days) |
| `get_daily` | boolean | `True` | Sync daily official consumption matching official daily totals |
| `get_estimation` | boolean | `True` | Sync current period consumption and cost estimation |
| `get_bill` | boolean | `True` | Sync historical issued bills (past 14 months) |
| `renewable_energy_sensor_enable` | boolean | `False` | Enable [Renewable Energy Feed-in Tariff (FiT)](https://www.clp.com.hk/en/business/low-carbon-solutions/renewable-energy/feed-in-tariff-business/application) tracking |
| `renewable_energy_sensor_name` | string | `CLP Renewable Energy` | Renewable energy sensor name |
| `renewable_energy_sensor_get_bill` | boolean | `True` | Sync FiT generation billing records |
| `renewable_energy_sensor_get_daily` | boolean | `True` | Sync daily renewable generation data |
| `renewable_energy_sensor_get_hourly` | boolean | `True` | Sync hourly renewable generation data |
| `renewable_energy_sensor_get_hourly_days` | int | `2` | Number of days of renewable hourly data to fetch |

---

## Tiered Pricing & Billing Semantics

### 1. CLP Official Bi-Monthly Tiers (Default Auto-Sync)
Residential electricity in Hong Kong is billed on a bi-monthly progressive scale:
- **Tier 1**: First 400 kWh @ HK$0.945 / kWh
- **Tier 2**: Next 600 kWh (401–1,000 kWh) @ HK$1.079 / kWh
- **Tier 3**: Next 800 kWh (1,001–1,800 kWh) @ HK$1.237 / kWh
- **Tier 4**: Next 800 kWh (1,801–2,600 kWh) @ HK$1.545 / kWh
- **Tier 5**: Next 800 kWh (2,601–3,400 kWh) @ HK$1.774 / kWh
- **Tier 6**: Next 800 kWh (3,401–4,200 kWh) @ HK$1.878 / kWh
- **Tier 7**: Above 4,200 kWh @ HK$1.890 / kWh

### 2. CLP Official Energy Saving Rebate
Applicable to residential accounts with total bi-monthly consumption of 400 kWh or less:
- **1 to 200 kWh**: 17.2 cents rebate per total kWh consumed (HK$0.172 / kWh)
- **201 to 300 kWh**: 16.2 cents rebate per total kWh consumed (HK$0.162 / kWh)
- **301 to 400 kWh**: 15.2 cents rebate per total kWh consumed (HK$0.152 / kWh)
- **Above 400 kWh**: No energy saving rebate.

### 3. Pro-Rata Scaling
When billing period days fall outside 55–65 days, tier block limits scale proportionally by `Days / 60.0`, matching CLP official billing methodology.

---

## Re-authentication & Re-login

### Automatic Token Rotation
Tokens are rotated in the background using the CLP refresh API.

### Native Re-authentication
If CLP invalidates your session, Home Assistant displays a **"Reconfigure"** badge. Click Reconfigure, paste your fresh tokens, and synchronization will resume instantly without data loss.

---

## Troubleshooting & Debugging

- **Enable Debug Logging**: Add to your `configuration.yaml` and restart Home Assistant:
  ```yaml
  logger:
    default: info
    logs:
      custom_components.clphk: debug
  ```

---

## Community & Unofficial Support

- **Telegram Group**: https://t.me/smarthomehk

---

## Tested On

- Home Assistant Container 2026.11+
- Python 3.13 / 3.14
- Linux aarch64 & x86_64

---

## Authors & Maintainers

* **Author & Original Creator**: [@thematrixdev](https://github.com/thematrixdev)
* **Contributor & Co-Maintainer**: [@kanshurichard](https://github.com/kanshurichard)

