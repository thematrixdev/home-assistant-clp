# CLP (HK) Statistic Home-Assistant Custom-Component

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

1. Sign in on CLP website: https://www.clp.com.hk/services/en/login
2. Open Chrome DevTools (`F12`)
3. Go to `Application` -> `Storage` -> `Local Storage`
4. Select `https://www.clp.com.hk`
5. Copy these keys:
   - `act` -> use as `Access Token`
   - `rct` -> use as `Refresh Token`

You can paste either:
- Full JSON object (recommended), for example `{"data":"...","time":...,"expire":"..."}`
- JSON string value, for example `"..."` (including quotes)
- Plain base64 token string, for example `...`

#### Accepted token formats

For both `Access Token` and `Refresh Token`, only these formats are accepted:

1. JSON object:
   `{"data":"<base64-token>","time":...,"expire":"..."}`
2. JSON string:
   `"<base64-token>"`
3. Plain base64 string:
   `<base64-token>`

### Configure in Home-Assistant

| Key                                       | Type    | Required | Accepted Values                              | Default                  | Description                                                                         |
|-------------------------------------------|---------|----------|----------------------------------------------|--------------------------|-------------------------------------------------------------------------------------|
| `access_token`                            | string  | *        | Accepted token formats above                 | (N/A)                    | CLP access token                                                                    |
| `refresh_token`                           | string  | *        | Accepted token formats above                 | (N/A)                    | CLP refresh token                                                                   |
| `name`                                    | string  |          | Any string                                   | `CLP`                    | Name of the sensor                                                                  |
| `timeout`                                 | int     |          | Any integer                                  | `30`                     | Connection timeout in second                                                        |
| `retry_delay`                             | int     |          | Any integer                                  | `300`                    | Delay before retry in second                                                        |
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

### Automatic re-login

No extra setup is required for automatic refresh.

If refresh returns HTTP `4xx`:
- tokens are cleared
- a persistent notification is shown in Home Assistant frontend
- the integration is unloaded (stopped) for safety

At that point, reconfigure with fresh tokens.

## Others

### Common problem

- More than one `clphk` entry will cause issues. Avoid multiple entries.
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
