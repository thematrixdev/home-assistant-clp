# CLP (HK) Statistic Home-Assistant Custom-Component 

## Prerequisite
- CLP Subscriber
- CLP smart meter installed
- CLP website credentials

## For `Home Assistant Container`
1. Download `custom_components/clp` here
2. SSH or SFTP into your Home-Assistant server
3. Locate `configuration.yaml`
4. Locate `custom_components` in the same directory. Create it if not exist 
5. Put the downloaded `clp` into `custom_components`
6. Restart Home-Assistant

## For `Home Assistant Operating System (with HACS)`
1. Setup `HACS` https://hacs.xyz/docs/setup/prerequisites
2. In `Home Assistant`, click `HACS` on the menu on the left
3. Select `integrations`
4. Click the menu button in the top right hand corner
5. Choose `custom repositories`
6. Enter `https://github.com/thematrixdev/home-assistant-clp` and choose `Integration`, click `ADD`
7. Find and click on `CLP` in the `custom repositories` list
8. Click the `DOWNLOAD` button in the bottom right hand corner
9. Restart Home-Assistant

## Configure in Home-Assistant
1. Add these in `configuration.yaml`
```
sensor:
  - platform: clp
    name: 'CLP' # whatever name you like
    username: '' # CLP web site username
    password: '' # CLP web site password
    timeout: 30 # connection timeout in second
    scan_interval: 3600 # how often to refresh data, in second
```
2. Restart Home-Assistant

## Common problem
- For slower hardware device, `TIMEOUT` may happen. Increase `timeout` in `configuration.yaml`

## Development environment
- Ubuntu 22.04

## Testing environment
- Home Assistant Container 2022.7.5
- Home Assistant Operating System 2022.8.7