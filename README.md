# CLP (HK) Statistic Home-Assistant Custom-Component

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

## Table of Content

- [Installation](#installation)
  - [Prerequisite](#prerequisite)
  - [Add to HACS](#add-to-hacs)
  - [Install](#install)
- [Configuration](#configuration)
  - [Configuration flow](#configuration-flow)
    - [Get tokens from Chrome](#get-tokens-from-chrome)
  - [Configure in Home-Assistant](#configure-in-home-assistant)
- [Re-login](#re-login)
  - [Manual re-login](#manual-re-login)
  - [Automatic re-login](#automatic-re-login)
- [Others](#others)
  - [Common problem](#common-problem)
  - [Debug](#debug)
    - [Basic](#basic)
    - [Advanced](#advanced)
  - [Support](#support)
  - [Unofficial support](#unofficial-support)
  - [Tested on](#tested-on)

## Installation
### Prerequisite

- CLP Subscriber
- CLP website credentials
- CLP smart meter installed (for `HOURLY` usage data)

### Add to HACS

1. Setup `HACS` https://hacs.xyz/docs/setup/prerequisites
2. In `Home Assistant`, click `HACS` on the menu on the left
3. Select `integrations`
4. Click the menu button in the top right hand corner
5. Choose `custom repositories`
6. Enter `https://github.com/thematrixdev/home-assistant-clp` and choose `Integration`, click `ADD`
7. Find and click on `CLPHK` in the `custom repositories` list
8. Click the `DOWNLOAD` button in the bottom right hand corner
9. Restart Home Assistant

### Install

1. Go to `Settings`, `Devices and Services`
2. Click the `Add Integration` button
3. Search `CLPHK`
4. Go through the configuration flow

## Configuration

### Configuration flow

1. Open `Settings` -> `Devices and Services` -> `CLPHK`
2. Step 1: Enter `Access Token` and `Refresh Token`
3. Step 2: Configure sensor options

#### Get tokens from Chrome

1. Open an **Incognito window** (`Ctrl+Shift+N` or `Cmd+Shift+N`)
2. Go to https://www.clp.com.hk/services/en/login and sign in
3. Open Chrome DevTools (`F12` or right click -> `Inspect`)
4. Switch to the **Console** tab, paste and execute:
   ```javascript
   console.log("Access Token:\n" + localStorage.getItem("act") + "\n\nRefresh Token:\n" + localStorage.getItem("rct"));
   ```
5. Copy the entire printed text from the console.
6. **Close the Incognito window directly** (do NOT click "Sign Out").
7. In Home Assistant, paste the copied block into the **"Paste All Tokens (One-Click)"** box.

*(Alternatively, you can manually copy `act` and `rct` from DevTools `Application` -> `Storage` -> `Local Storage` -> `https://www.clp.com.hk`)*

> **WARNING**: Do NOT sign out from the CLP website. Signing out will revoke the refresh token and the integration will stop working. Always close the browser window directly after copying the tokens.

#### One-Click Paste & Accepted token formats

In the configuration and re-authentication dialogs, you can simply paste the full copied text into the **"Paste All Tokens (One-Click)"** field. The integration auto-parses:
- Labeled console text containing both `Access Token:` and `Refresh Token:`
- Single JSON dict containing `act`/`rct` or `access_token`/`refresh_token`
- Two separate JSON objects `{"data":"...","time":...,"expire":"..."}`
- Plain Base64 token lines

If entering separate fields manually, both `Access Token` and `Refresh Token` accept:
1. JSON object: `{"data":"<base64-token>","time":...,"expire":"..."}`
2. JSON string: `"<base64-token>"`
3. Plain base64 string: `<base64-token>`

### Home Assistant Energy Dashboard Integration

Because CLP electricity data is naturally delayed by ~3 hours, importing readings at collection time causes hourly graphs to shift by 3 hours. 

This integration automatically backfills **Home Assistant Long-Term Statistics** (`clphk:main_hourly_energy`, named `CLP Hourly Energy`) with exact historical hourly timestamps directly from CLP:
1. Go to **Settings** -> **Dashboards** -> **Energy**.
2. Under **Electricity Grid**, click **Add Consumption**.
3. Choose statistic **CLP Hourly Energy** (`clphk:main_hourly_energy`).
4. Your hourly grid consumption will align accurately with true historical usage!

### Configure in Home-Assistant

| Key                                       | Type    | Required | Accepted Values                              | Default                  | Description                                                                         |
|-------------------------------------------|---------|----------|----------------------------------------------|--------------------------|-------------------------------------------------------------------------------------|
| `access_token`                            | string  | *        | Accepted token formats above                 | (N/A)                    | CLP access token                                                                    |
| `refresh_token`                           | string  | *        | Accepted token formats above                 | (N/A)                    | CLP refresh token                                                                   |
| `name`                                    | string  |          | Any string                                   | `CLP`                    | Name of the sensor                                                                  |
| `timeout`                                 | int     |          | Any integer                                  | `30`                     | Connection timeout in second                                                        |
| `type`                                    | string  |          | ` `<br/>`BIMONTHLY`<br/>`DAILY`<br/>`HOURLY` | ` `                      | Type of data to be shown in state<br/>If not specified, best accurate value is used |
| `get_account`                             | boolean |          | `True`<br/>`False`                           | `False`                  | Get account summary                                                                 |
| `get_bill`                                | boolean |          | `True`<br/>`False`                           | `False`                  | Get bills                                                                           |
| `get_estimation`                          | boolean |          | `True`<br/>`False`                           | `False`                  | Get usage estimation                                                                |
| `get_bimonthly`                           | boolean |          | `True`<br/>`False`                           | `False`                  | Get bi-monthly usage                                                                |
| `get_daily`                               | boolean |          | `True`<br/>`False`                           | `False`                  | Get daily usage                                                                     |
| `get_hourly`                              | boolean |          | `True`<br/>`False`                           | `False`                  | Get hourly usage                                                                    |
| `get_hourly_days`                         | int     |          | `1` or `2`                                   | `1`                      | Number of days to get hourly data                                                   |
| `renewable_energy_sensor_enable`          | boolean |          | `True`<br/>`False`                           | `False`                  | Enable renewable energy sensor                                                      |
| `renewable_energy_sensor_name`            | string  |          | `True`<br/>`False`                           | `'CLP Renewable Energy'` | Name of the renewable energy sensor                                                 |
| `renewable_energy_sensor_type`            | string  |          | ` `<br/>`BIMONTHLY`<br/>`DAILY`<br/>`HOURLY` | ` `                      | Type of data to be shown in state<br/>If not specified, best accurate value is used |
| `renewable_energy_sensor_get_bill`        | boolean |          | `True`<br/>`False`                           | `False`                  | Get energy generation in bills                                                      |
| `renewable_energy_sensor_get_daily`       | boolean |          | `True`<br/>`False`                           | `False`                  | Get daily energy generation                                                         |
| `renewable_energy_sensor_get_hourly`      | boolean |          | `True`<br/>`False`                           | `False`                  | Get hourly energy generation                                                        |
| `renewable_energy_sensor_get_hourly_days` | int     |          | `1` or `2`                                   | `1`                      | Number of days to get hourly data                                                   |

- It is recommended to provide `type` and `renewable_energy_sensor_type` for data consistency

## Re-login

This integration uses `access_token` + `refresh_token`.

### Manual re-login

1. Go to `Settings`, `Devices and Services`
2. Click `CLPHK`
3. Click `Configure`
4. Fill in new `Access Token` and `Refresh Token`
5. Click `Submit`

### Automatic re-login & Re-authentication

No extra setup is required for automatic refresh.

If refresh returns HTTP `4xx` or tokens expire:
- Tokens are cleared and a persistent notification is shown in the Home Assistant frontend.
- A **native Re-authentication flow** is automatically triggered in Home Assistant, displaying a "Reconfigure" card on the integration.
- Simply click "Reconfigure", paste fresh tokens into the one-click input box, and data sync will instantly resume without needing to reinstall.

## Others

### Common problem

- More than one `clphk` entry will cause issues. Avoid multiple entries.
- If your CLP login owns more than one account, only the first active account is reported; the rest are ignored (a warning is logged).
- Timeouts may occur on slower hardware. Increase `timeout` value to mitigate.
- If you see `CLPHK Authentication Failed` notification, refresh token was rejected by CLP and the integration was stopped. Reconfigure with new tokens.

### Debug

#### Basic

- On Home Assistant, go to `Settigns` -> `Logs`
- Search `CLPHK`

#### Advanced

- Add these lines to `configuration.yaml`

```yaml
logger:
  default: info
  logs:
    custom_components.clphk: debug
```

- Restart Home Assistant
- On Home Assistant, go to `Settigns` -> `Logs`
- Search `CLPHK`
- Click the `LOAD FULL LOGS` button

### Support

- Open an issue on GitHub
- Specify:
    - What's wrong
    - Home Assistant version
    - CLP custom-integration version
    - Configuration (without sensitive data)
    - Logs

### Unofficial support

- Telegram Group https://t.me/smarthomehk

### Tested on

- Ubuntu 24.04
- Home Assistant Container 2025.6.1
