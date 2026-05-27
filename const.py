"""Constants for the Controlart Wired Relay integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import Platform

DOMAIN = "controlart_wired_relay"

CONF_MAC3 = "mac3"
CONF_MAC4 = "mac4"
CONF_MAC5 = "mac5"
CONF_INTERLOCK_DELAY_MS = "interlock_delay_ms"
CONF_INTERLOCK_PAIRS = "interlock_pairs"
CONF_SCAN_INTERVAL = "scan_interval"

ATTR_DURATION_MS = "duration_ms"

EVENT_KEYPAD = "controlart_wired_relay_keypad_event"

DEFAULT_NAME = "Controlart Wired Relay"
DEFAULT_PORT = 4998
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_TIMEOUT = 5.0
DEFAULT_PULSE_DURATION_MS = 500
DEFAULT_INTERLOCK_DELAY_MS = 500
MAX_PULSE_DURATION_MS = 10000
MAX_INTERLOCK_DELAY_MS = 5000
MIN_PULSE_DURATION_MS = 100
MIN_INTERLOCK_DELAY_MS = 100
INPUT_COUNT = 12
INTEGRATION_VERSION = "0.2.1"
OUTLET_COUNT = 10

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

MANUFACTURER = "Controlart"
MODEL = "MD-ETH-MCRL2"
SERVICE_PULSE_OUTPUT = "pulse_output"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


def parse_interlock_pairs(value: Any) -> list[tuple[int, int]]:
    """Parse interlock pair lines like 0-1."""
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split("-", 1)
        if len(parts) != 2:
            raise ValueError("invalid interlock pair")

        first = int(parts[0].strip())
        second = int(parts[1].strip())
        if (
            first == second
            or first < 0
            or second < 0
            or first >= OUTLET_COUNT
            or second >= OUTLET_COUNT
        ):
            raise ValueError("interlock pair out of range")

        pair = tuple(sorted((first, second)))
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)

    return pairs
