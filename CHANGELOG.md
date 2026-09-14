# Changelog

## 0.2.4

- Enforced non-overlapping interlock pairs and made operations within each pair atomic.
- Confirmed the peer output is off before enabling an interlocked output, including rechecks during the configured delay.
- Prevented new output operations while the coordinator is stopping and synchronized the interlock safety fallback with normal commands.
- Corrected initial config-flow unique-ID handling and added TCP port validation coverage.
- Added concurrency, shutdown, and safety tests for logical interlocks.

## 0.2.3

- Corrigido `interlock_pairs` no Options Flow para ser opcional e aceitar valor vazio.
- Corrigidos os catálogos completos de tradução do Options Flow em inglês e português do Brasil.
- Adicionados testes para o schema opcional e para salvar sem pares de intertravamento.

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
