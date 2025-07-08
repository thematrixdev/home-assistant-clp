# CLP (HK) Statistic Home-Assistant Custom-Component

## Table of Content

- [Installation](#installation)
  - [Prerequisite](#prerequisite)
  - [Add to HACS](#add-to-hacs)
  - [Install](#install)
- [Configuration](#configuration)
  - [Configuration flow](#configuration-flow)
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

***Starting from 21st June 2025, sign-in with `username` and `password` no long works.***

1. Visit CLP sign-in page [中文](https://www.clp.com.hk/services/zh/login) / [English](https://www.clp.com.hk/services/en/login)
2. Choose to Sign-in with ***email***
3. Enter your email address. Click `Continue`
4. Get the one-time-password (OTP) from email. ***DO NOT*** continue signing-in on CLP webpage.
5. Enter the OTP during the configuration flow

### Configure in Home-Assistant

| Key                                       | Type    | Required | Accepted Values                              | Default                  | Description                                                                         |
|-------------------------------------------|---------|----------|----------------------------------------------|--------------------------|-------------------------------------------------------------------------------------|
| `email`                                   | string  | *        | Any string                                   | (N/A)                    | CLP username or account number                                                      |
| `otp`                                     | string  | *        | Any string                                   | (N/A)                    | CLP account password                                                                |
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

This integration exchanges the `OTP` for a `token`.

However, the `token` may get invalidated from time to time.

### Manual re-login

1. Go to `Settings`, `Devices and Services`
2. Click `CLPHK`
3. Click `Configure`
4. Fill in the new `OTP`
5. Click `Submit`

### Automatic re-login

1. Install `IMAP` integration https://www.home-assistant.io/integrations/imap
2. Configure `IMAP` integration
  - On `Message data to be included in the imap_content event data`, check `Body text`
3. Update `configuration.yaml`
   - how to update `configuration.yaml`: https://www.home-assistant.io/docs/configuration/
   - add the following:

```yaml
template:
  - trigger:
      - platform: event
        event_type: "imap_content"
        id: "clp_email_otp_event"
        event_data:
          sender: "otp@info.clp.com.hk"
    sensor:
      - name: clp_email_otp
        state: "{{ trigger.event.data['text'] | regex_findall('(\\d{6})') | first }}"
        attributes:
          Date: "{{ trigger.event.data['date'] }}"
```
4. Restart Home Assistant

## Others

### Common problem

- More than one `clphk` entry will cause issues. Avoid multiple entries.
- Timeouts may occur on slower hardware. Increase `timeout` value to mitigate.

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
