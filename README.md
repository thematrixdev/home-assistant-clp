# CLP (HK) Statistic Home-Assistant Custom-Component 

## Prerequisite
- CLP Subscriber
- CLP smart meter installed
- CLP website credentials

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
1. Add these in `configuration.yaml`
```
sensor:
  - platform: clp
    name: 'CLP' # whatever name you like
    username: '' # CLP web site username
    password: '' # CLP web site password
    timeout: 30 # connection timeout in second
    type: '' # type of data to be shown in state
```
- Possible values for `type`:
  - BIMONTHLY
  - DAILY
  - HOURLY
  - (EMPTY: best accurate value)
2. Restart Home-Assistant

## Common problem
- Single entity only. More than one `clp` entry will cause problems
- For slower hardware device, `TIMEOUT` may happen. Increase `timeout` in `configuration.yaml`

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
- Ubuntu 22.04
- Home Assistant Container 2024.6.2

## Unofficial support
https://t.me/smarthomehk
