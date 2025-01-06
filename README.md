# CLP (HK) Statistic Home-Assistant Custom-Component

## Prerequisite

- CLP Subscriber
- CLP website credentials
- CLP smart meter installed (for `HOURLY` usage data)

## Add to HACS

1. Setup `HACS` https://hacs.xyz/docs/setup/prerequisites
2. In `Home Assistant`, click `HACS` on the menu on the left
3. Select `integrations`
4. Click the menu button in the top right hand corner
5. Choose `custom repositories`
6. Enter `https://github.com/thematrixdev/home-assistant-clp` and choose `Integration`, click `ADD`
7. Find and click on `CLPHK` in the `custom repositories` list
8. Click the `DOWNLOAD` button in the bottom right hand corner
9. Restart Home-Assistant ***(You have to restart before proceeding)***

## Install

1. Go to `Settings`, `Devices and Services`
2. Click the `Add Integration` button
3. Search `CLPHK`
4. Go through the configuration flow

## Configure in Home-Assistant

| Key                                       | Type    | Required | Accepted Values                              | Default                  | Description                                                                         |
|-------------------------------------------|---------|----------|----------------------------------------------|--------------------------|-------------------------------------------------------------------------------------|
| `username`                                | string  | *        | Any string                                   | (N/A)                    | CLP username or account number                                                      |
| `password`                                | string  | *        | Any string                                   | (N/A)                    | CLP account password                                                                |
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

## Common problem

- More than one `clp` entry will cause issues. Avoid multiple entries.
- Timeouts may occur on slower hardware. Increase `timeout` in `configuration.yaml` to mitigate.

## Debug

### Basic

- On Home Assistant, go to `Settigns` -> `Logs`
- Search `CLP`

### Advanced

- Add these lines to `configuration.yaml`

```yaml
logger:
  default: info
  logs:
    custom_components.clp: debug
```

- Restart Home Assistant
- On Home Assistant, go to `Settigns` -> `Logs`
- Search `CLP`
- Click the `LOAD FULL LOGS` button

## Support

- Open an issue on GitHub
- Specify:
    - What's wrong
    - Home Assistant version
    - CLP custom-integration version
    - Configuration (without sensitive data)
    - Logs

## Unofficial support

- Telegram Group https://t.me/smarthomehk

## Tested on

- Ubuntu 24.10
- Home Assistant Container 2024.10
