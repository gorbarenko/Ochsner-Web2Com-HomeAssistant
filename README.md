# Ochsner Web2Com for Home Assistant

Custom Home Assistant integration for locally connected Ochsner Web2Com gateways.

## Features

- Local SOAP communication over HTTP with Digest or Basic authentication.
- Configuration through **Settings → Devices & services → Add integration → Ochsner Web2Com**.
- Thirteen predefined temperature, heating-circuit and energy sensors.
- Device entry with grouped entities in Home Assistant.
- Heater mode switch: **Manual** (`4`) / **Automatic** (`1`). **Warning:** changes can energize electric heaters.
- Independent polling intervals for each sensor (15–300 seconds).

## Install with HACS

1. Publish this repository on GitHub with `custom_components/web2com/` in the repository root.
2. Open HACS → **Custom repositories**, paste the GitHub repository URL, select **Integration** and add it.
3. Install **Ochsner Web2Com** from HACS, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Ochsner Web2Com** and enter the gateway address, username, password, and authentication method.

## Notes

- Configuration credentials are supplied in the Home Assistant setup form; this repository contains no device credentials.
- Communication is local **unencrypted HTTP**. Use a trusted home network.
- The OID map can vary between gateway/controller models. Check readings against the gateway interface.
- Heater mode writes use SOAP `writeDpRequest` and must be tested carefully before routine use.
- This is a community custom integration; it has not been tested with every gateway firmware or Home Assistant release.

## Languages

English, German, Ukrainian, French, Italian, Dutch, Polish, Czech, Slovak and Slovenian. Russian is not included. Device entity identifiers are generated for each gateway and do not contain user-specific labels.
