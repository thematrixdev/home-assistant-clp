# CLP (HK) Statistic Home-Assistant Custom-Component 

## Prerequisite
- CLP Subscriber
- CLP smart meter installed
- CLP website credentials

## For `Home Assistant Container`
Use an image like this:
```
FROM ghcr.io/home-assistant/home-assistant:stable
RUN apk add icu-data-full firefox
RUN pip3 install selenium webdriver-manager
```
2. Follow the `Install the component` step

## For `Home Assistant Operating System`

1. Click on your username on UI
2. Turn on `Advanced Mode` on the right
3. Go to `Add-ons` -> `Add-on store`
4. Install `SSH & Web Terminal` (the community version)
5. On `Info` tab of `SSH & Web Terminal`, turn off `Protection mode`
6. On `Configuration` tab, enter a `password`, change `sftp` to `true`
7. On `Configuration` tab, turn on `share_sessions`. `Save`
8. On `Info` tab click `START`
9. SSH to `hassio@IP` with the configured password
10. Run : `docker exec -ti homeassistant apk add icu-data-full firefox`
11. Follow the `Install the component` step

## Install the component
1. Download `custom_components/clp` here
2. SSH or SFTP into your Home-Assistant server
3. Locate `configuration.yaml`
4. Locate `custom_components` in the same directory. Create it if not exist 
5. Put the downloaded `clp` into `custom_components`
6. Restart Home-Assistant

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

## Debug
1. SSH and run:
```
docker logs -f homeassistant
```
2. Locate `[WDM]` and observe if there is any error message afterwards:
```
[WDM] - Downloading: 16.2kB [00:00, 8.22MB/s]
```
3. In Home Assistant find `sensor.clp`

## Development environment
- Ubuntu 22.04

## Testing environment
- Home Assistant Container 2022.7.5 on x64
- Home Assistant Operating System 2022.8.7 on VirtualBox