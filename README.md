![OCHSNER](custom_components/web2com/brand/logo.svg)

# Ochsner Web2Com for Home Assistant

Local integration for Ochsner Room Terminal / Web2Com. Version **1.9.1**, integration domain **`web2com`**.

## Requirements

- Home Assistant **2024.12 or newer**.
- An accessible Web2Com gateway on your local network, with a username and password.
- HTTP with Digest or Basic authentication. IPv4 addresses and hostnames are supported, optionally followed by a port. HTTPS and IPv6 are not supported in this version.
- Local integration logos require Home Assistant **2026.3 or newer**.

The supplied address map assigns `/1/2/4/...` to heating circuit 1, `/1/2/5/...` to heating circuit 2, and `/1/2/2/...` to electric heaters. Check these assignments against your controller: other models or configurations may use a different map.

## Installation with HACS

1. Open **HACS → Custom repositories**.
2. Add `https://github.com/gorbarenko/Ochsner-Web2Com-HomeAssistant` with category **Integration**.
3. Download **Ochsner Web2Com**. Version 1.9.1 will be available once published in that repository.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → Ochsner Web2Com**.
6. Enter the gateway hostname or IPv4 address **without `http://`**, your username and password, and the authentication method.

## Manual installation

1. Extract the release ZIP.
2. Copy the entire `custom_components/web2com` folder into `/config/custom_components/`.
3. Check that `/config/custom_components/web2com/manifest.json` exists. Do not add an extra repository folder between `custom_components` and `web2com`.
4. Restart Home Assistant and add the integration as described above.

Only `custom_components/web2com` belongs in your Home Assistant configuration. The root README, license and `hacs.json` are repository files.

## Updating an existing installation

1. Back up Home Assistant, including its configuration and history database.
2. Update through HACS, or replace the entire `/config/custom_components/web2com` folder with the new version.
3. Restart Home Assistant. **Do not remove and re-add the integration.**
4. Allow approximately one minute for initial readings; slow connections may take longer.

Existing primary entity identifiers are retained. Duplicate sensors within the same circuit are consolidated; redundant registry entries are disabled without deleting their previous history. Separate histories are not merged. To roll back after upgrading, restore the complete backup rather than only the old integration files.

## Devices and sensors

The integration groups entities into four devices:

| Device | Contents |
|---|---|
| Circuit 1 — underfloor heating | Circuit temperatures, pump, heating curve and operating mode |
| Circuit 2 — radiators | Circuit temperatures, pump, heating curve and operating mode |
| Electric heaters | Heater mode, buffer temperature, starts, operating hours and energy |
| Room Terminal | Parent device and an overall stale-data indicator |

Device labels currently use Ukrainian names for the circuits and heaters. Entity names and controls include English and Ukrainian translations.

Additional diagnostic sensors are disabled by default. Enable the ones you need under **Settings → Devices & services → Entities**. Optional discovery can be enabled in the integration's configuration options. It only reads known controller branches; newly discovered sensors are disabled by default. Previously discovered sensors are retained when discovery is turned off.

## Temperature and mode controls

Each circuit provides temperature controls for the heating curve, design temperatures, heating limit, day/night settings and manual-mode setpoint. Mode selectors are provided for both circuits and electric heaters.

Controls remain unavailable until the gateway supplies valid write permissions and the required limits or supported modes. Before every write, the integration reads these permissions again and checks the requested value against the controller's range and step. After writing, it reads the value back to confirm the change.

- Circuit modes: standby, automatic, normal heating, economy heating and manual — only those confirmed by the controller are offered.
- Electric heater modes: automatic and manual. **Off is displayed as a sensor state, but is not offered as a write command**, because support for writing that mode has not been confirmed.
- A failed or timed-out write is not automatically repeated. Check the actual controller setting before trying again.

Hardware write testing has not been performed for this release. Verify readings and parameter meanings against your controller before using controls.

## Connection failures and stale data

When a read fails, the last successful value is retained. A retained value does **not** confirm the current physical state.

Each device has a **Stale data** indicator. The Room Terminal indicator covers all active readings. Sensor attributes include `last_success`, `stale` and `last_error`. Use the indicator or `stale` attribute in automations that depend on fresh readings.

Readings are staggered to reduce gateway load. Update intervals vary from 15 to 300 seconds, with longer delays after repeated failures. Last successful readings are cached across restarts; a new sensor without any successful reading remains unavailable.

## Troubleshooting

- **Cannot connect:** check the gateway address, network access, credentials and authentication method.
- **Missing diagnostic sensors:** enable the required entities in the entity list.
- **Unavailable controls:** the controller may not provide writable access, valid temperature limits or a supported mode list. Values are not guessed.
- **Old values remain visible:** inspect the Stale data indicator and `last_success` timestamp.
- **Logo does not appear:** local integration images require HA 2026.3+. Restart HA and refresh the browser after updating.

For support, open an [issue](https://github.com/gorbarenko/Ochsner-Web2Com-HomeAssistant/issues) with your Home Assistant version, controller model and relevant error messages. Remove passwords and other private information before sharing logs.
