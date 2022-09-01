# CLP (HONG KONG) Statistic Home-Assistant Custom-Component 

## Prerequisite
- CLP Subscriber
- CLP smart meter installed
- CLP website credentials

## Install necessary packages
- SSH to Home-Assistant
```
apk add icu-data-full firefox
pip3 install selenium webdriver-manager
```

## Install Home-Assistant Custom-Component
- Download `custom_components/clp` here
- SSH or SFTP into your Home-Assistant server
- Locate `configuration.yaml`
- Locate `custom_components` in the same directory. Create it if not exist 
- Put the downloaded `clp` into `custom_components`
- Restart Home-Assistant

## Configure Sesame-Lock in Home-Assistant
- Add these in `configuration.yaml`
```
sensor:
  - platform: clp
    name: 'WHATEVER_NAME'
    username: 'CLP_USERNAME'
    password: 'CLP_PASSWORD'
    scan_interval: 3600
```
- Restart Home-Assistant

## Development environment
- Ubuntu 22.04

## Testing environment
- x64
- Home Assistant Container 2022.7.5