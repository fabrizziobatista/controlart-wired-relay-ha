# Controlart Wired Relay

Custom Home Assistant integration for Controlart MD-ETH-MCRL2 wired relay modules.

This integration communicates locally with the module over TCP, exposes relay outputs and inputs, listens for asynchronous module updates, and provides helper diagnostics and services for automation.

## Features

- Config flow setup from the Home Assistant UI.
- Automatic discovery of MAC3/MAC4/MAC5 using `get_mac_addr`.
- 10 relay output switches: `OUT0` through `OUT9`.
- 12 binary input sensors: `IN0` through `IN11`.
- Continuous TCP listener for asynchronous `setcmd` updates.
- Polling fallback for health/state refresh.
- Diagnostic sensors:
  - Connection Status
  - Last Update
  - Last Error
- `pulse_output` service for timed relay pulses.
- Optional logical interlock pairs for output safety.
- CAN keypad bus events and visual device triggers for known keypad events.

## Installation

### HACS Installation

This repository is prepared for HACS as a custom repository.

1. Open **HACS > Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add this repository URL.
4. Select category **Integration**.
5. Search for **Controlart Wired Relay** and install it.
6. Restart Home Assistant.
7. Go to **Settings > Devices & services > Add integration**.
8. Search for **Controlart Wired Relay**.

### Manual Installation

1. Copy the folder:

   ```text
   custom_components/controlart_wired_relay
   ```

   into your Home Assistant config directory as:

   ```text
   config/custom_components/controlart_wired_relay
   ```

2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**.
4. Search for **Controlart Wired Relay**.

## Screenshots

Screenshots will be added after the first packaged release.

### Device Page

Placeholder: device page showing outputs, inputs, diagnostics, and device triggers.

### Configuration Flow

Placeholder: config flow showing host, port, optional MAC fields, and options.

### Automations

Placeholder: visual automation editor showing input and keypad device triggers.

## Configuration

Required fields:

- `host`: IP address or hostname of the module.
- `port`: TCP port. Default is `4998`.
- `name`: Device name shown in Home Assistant.

Optional fields:

- `mac3`
- `mac4`
- `mac5`

If the MAC fields are left empty, the integration sends:

```text
get_mac_addr
```

and expects a response like:

```text
macaddr_RT,6D-08-CA
```

The integration stores MAC fields as two-digit uppercase hexadecimal values, but sends relay commands using decimal MAC values as required by the module.

## Entities

### Switches

- `{device_name} OUT0`
- `{device_name} OUT1`
- ...
- `{device_name} OUT9`

### Binary Sensors

- `{device_name} IN0`
- `{device_name} IN1`
- ...
- `{device_name} IN11`

### Diagnostic Sensors

- `{device_name} Connection Status`
  - `connected`
  - `disconnected`
  - `reconnecting`
- `{device_name} Last Update`
- `{device_name} Last Error`

## Service: pulse_output

Service:

```text
controlart_wired_relay.pulse_output
```

Fields:

- `entity_id`: output switch entity from this integration.
- `duration_ms`: pulse duration in milliseconds.
  - Default: `500`
  - Minimum: `100`
  - Maximum: `10000`

Example:

```yaml
service: controlart_wired_relay.pulse_output
data:
  entity_id: switch.relay_out0
  duration_ms: 500
```

The integration rejects concurrent pulses on the same output channel.

## Interlock

Interlock pairs can be configured in the integration options.

Example:

```text
0-1
2-3
```

When turning on one output in a configured pair, the integration first turns off the other output, waits `interlock_delay_ms`, then turns on the requested output.

If a module update reports both outputs in a pair as on, the integration logs a warning, records a diagnostic error, and attempts to turn both outputs off.

### Safety Notice

This is a logical software interlock only. It is not a substitute for proper electrical interlocking, contactors, overload protection, float switches, pressure switches, or other required safety devices.

For pumps, motors, transfer systems, or any load where simultaneous activation can cause equipment damage or unsafe operation, use a physical electrical interlock designed and installed by a qualified professional.

Critical loads must have independent physical protection. Do not rely on Home Assistant, TCP communication, Wi-Fi/Ethernet availability, or this integration as the only safety layer.

## Keypads

The TCP listener detects CAN keypad feedback lines:

```text
setcankpfb,TYP_ID,DEV_ID,EVT,KEY
```

Events are fired on the Home Assistant bus as:

```text
controlart_wired_relay_keypad_event
```

Event data:

- `config_entry_id`
- `typ_id`
- `dev_id`
- `key`
- `event`
- `raw`

Supported event names:

- `click`
- `double_click`
- `long_click`
- `press`
- `release`

The integration also exposes visual device triggers for the currently known keypad:

- `typ_id`: `02`
- `dev_id`: `01-0E-11`
- keys: `0`, `1`, `2`, `3`

No keypad entities are created yet.

## Troubleshooting

Enable debug logs:

```yaml
logger:
  logs:
    custom_components.controlart_wired_relay: debug
```

Useful checks:

- Confirm the module is reachable from Home Assistant.
- Confirm the TCP port is correct.
- Confirm MAC discovery works with `get_mac_addr`.
- Check `{device_name} Connection Status`.
- Check `{device_name} Last Error`.
- If outputs do not respond, confirm commands are using decimal MAC values internally.
- If fast input pulses are missed, confirm the listener is connected and receiving asynchronous `setcmd` lines.
