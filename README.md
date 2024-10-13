# CLP (HK) Statistic Home-Assistant Custom-Component

## Prerequisite

- CLP Subscriber
- CLP website credentials
- CLP smart meter installed (for `HOURLY` usage data)

## Install

1. Setup `HACS` https://hacs.xyz/docs/setup/prerequisites
2. In `Home Assistant`, click `HACS` on the menu on the left
3. Select `integrations`
4. Click the menu button in the top right hand corner
5. Choose `custom repositories`
6. Enter `https://github.com/thematrixdev/home-assistant-clp` and choose `Integration`, click `ADD`
7. Find and click on `CLP` in the `custom repositories` list
8. Click the `DOWNLOAD` button in the bottom right hand corner
9. Restart Home-Assistant ***(You have to restart before proceeding)***

## Configure in Home-Assistant

### Minimal configuration

```yaml
# configuration.yaml
sensor:
  - platform: clp
    username: !secret clp_username
    password: !secret clp_pw
    type: 'HOURLY'
```

```yaml
# secrets.yaml
clp_username: "YOUR_USERNAME"
clp_pw: "YOUR_VERY_SECURE_PASSWORD"
```

| Key                                  | Type    | Required | Accepted Values                              | Default                  | Description                                                                         |
|--------------------------------------|---------|----------|----------------------------------------------|--------------------------|-------------------------------------------------------------------------------------|
| `username`                           | string  | *        | Any string                                   | (N/A)                    | CLP account username                                                                |
| `password`                           | string  | *        | Any string                                   | (N/A)                    | CLP account password                                                                |
| `name`                               | string  |          | Any string                                   | `CLP`                    | Name of the sensor                                                                  |
| `timeout`                            | int     |          | Any integer                                  | `30`                     | Connection timeout in second                                                        |
| `retry_delay`                        | int     |          | Any integer                                  | `300`                    | Delay before retry in second                                                        |
| `type`                               | string  |          | ` `<br/>`DAILY`<br/>`HOURLY`                 | ` `                      | Type of data to be shown in state<br/>If not specified, best accurate value is used |
| `get_account`                        | boolean |          | `True`<br/>`False`                           | `False`                  | Get account summary                                                                 |
| `get_bill`                           | boolean |          | `True`<br/>`False`                           | `False`                  | Get bills                                                                           |
| `get_estimation`                     | boolean |          | `True`<br/>`False`                           | `False`                  | Get usage estimation                                                                |
| `get_daily`                          | boolean |          | `True`<br/>`False`                           | `False`                  | Get daily usage                                                                     |
| `get_hourly`                         | boolean |          | `True`<br/>`False`                           | `False`                  | Get hourly usage                                                                    |
| `renewable_energy_sensor_enable`     | boolean |          | `True`<br/>`False`                           | `False`                  | Enable renewable energy sensor                                                      |
| `renewable_energy_sensor_name`       | string  |          | `True`<br/>`False`                           | `'CLP Renewable Energy'` | Name of the renewable energy sensor                                                 |
| `renewable_energy_sensor_type`       | string  |          | ` `<br/>`BIMONTHLY`<br/>`DAILY`<br/>`HOURLY` | ` `                      | Type of data to be shown in state<br/>If not specified, best accurate value is used |
| `renewable_energy_sensor_get_bill`   | boolean |          | `True`<br/>`False`                           | `False`                  | Get energy generation in bills                                                      |
| `renewable_energy_sensor_get_daily`  | boolean |          | `True`<br/>`False`                           | `False`                  | Get daily energy generation                                                         |
| `renewable_energy_sensor_get_hourly` | boolean |          | `True`<br/>`False`                           | `False`                  | Get hourly energy generation                                                        |

- It is recommended to provide `type` and `renewable_energy_sensor_type` for data consistency

## Common problem

- More than one `clp` entry will cause issues. Avoid multiple entries.
- Timeouts may occur on slower hardware. Increase `timeout` in `configuration.yaml` to mitigate.

## Debug

- Configure `debug` level https://www.home-assistant.io/integrations/logger/
- SSH
- `docker logs -f homeassistant`
- Look for `CLP` wordings

## Use SSH on Home Assistant Operating System

1. Click on your username on UI
2. Turn on `Advanced Mode` on the right
3. Go to `Add-ons` -> `Add-on store`
4. Install `SSH & Web Terminal` (the community version)
5. On `Info` tab of `SSH & Web Terminal`, turn off `Protection mode`
6. On `Configuration` tab, enter a `password`, change `sftp` to `true`
7. On `Configuration` tab, turn on `share_sessions`. `Save`
8. On `Info` tab click `START`
9. SSH to `hassio@IP` with the configured password

## Tested on

- Ubuntu 24.10
- Home Assistant Container 2024.10

## Unofficial support

https://t.me/smarthomehk
