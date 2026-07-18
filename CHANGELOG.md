# Changelog

## 0.2.2

- Inserida possibilidade de configuracao do modulo apos instalado

## 0.2.1

- Fixed clearing `interlock_pairs` in the options flow. Empty input now disables configured interlocks.

## 0.2.0

- Added diagnostic sensors for connection status, last update, and last error.
- Added `pulse_output` service.
- Added optional logical interlock pairs.
- Added CAN keypad event handling.
- Added visual device triggers for inputs and known keypad events.
- Added continuous TCP listener for asynchronous module updates.

## 0.1.0

- Initial MVP.
- Added config flow setup.
- Added TCP communication.
- Added 10 output switches for `OUT0..OUT9`.
- Added 12 input binary sensors for `IN0..IN11`.
- Added polling via DataUpdateCoordinator.

