"""Config flow for Controlart Wired Relay."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_INTERLOCK_DELAY_MS,
    CONF_INTERLOCK_PAIRS,
    CONF_MAC3,
    CONF_MAC4,
    CONF_MAC5,
    CONF_SCAN_INTERVAL,
    DEFAULT_INTERLOCK_DELAY_MS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_INTERLOCK_DELAY_MS,
    MIN_INTERLOCK_DELAY_MS,
    parse_interlock_pairs,
)


def _clean_mac_part(value: Any) -> str:
    """Normalize one Controlart MAC field."""
    raw = str(value).strip().upper()
    if raw.startswith("$"):
        raw = raw[1:]
        base = 16
    elif raw.startswith("0X"):
        raw = raw[2:]
        base = 16
    elif any(char in "ABCDEF" for char in raw):
        base = 16
    else:
        base = 10

    if not raw:
        raise ValueError("empty MAC part")

    number = int(raw, base)
    if number < 0 or number > 255:
        raise ValueError("MAC part out of range")

    return f"{number:02X}"


def _mac_suffix(mac3: str, mac4: str, mac5: str) -> str:
    """Return the normalized unique module suffix."""
    return f"{mac3}_{mac4}_{mac5}"


def _clean_discovered_mac_part(value: str) -> str:
    """Normalize one discovered hexadecimal MAC field."""
    raw = value.strip().upper()
    if len(raw) != 2:
        raise ValueError("invalid discovered MAC part")

    number = int(raw, 16)
    if number < 0 or number > 255:
        raise ValueError("discovered MAC part out of range")

    return f"{number:02X}"


def _parse_discovered_mac(response: str) -> tuple[str, str, str]:
    """Parse macaddr_RT,MAC3-MAC4-MAC5 from a response block."""
    mac_line = next(
        (
            line.strip()
            for line in response.splitlines()
            if line.strip().startswith("macaddr_RT,")
        ),
        "",
    )
    if not mac_line:
        raise ValueError("macaddr_RT response not found")

    _, suffix = mac_line.split(",", 1)
    parts = suffix.split("-")
    if len(parts) != 3:
        raise ValueError("invalid macaddr_RT response")

    return tuple(_clean_discovered_mac_part(part) for part in parts)


async def _async_discover_mac(host: str, port: int) -> tuple[str, str, str]:
    """Discover MAC3/MAC4/MAC5 from the module."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=DEFAULT_TIMEOUT,
        )
    except (OSError, TimeoutError, asyncio.TimeoutError) as err:
        raise ValueError("unable to connect for MAC discovery") from err

    lines: list[str] = []
    try:
        writer.write(b"get_mac_addr\r\n")
        await asyncio.wait_for(writer.drain(), timeout=DEFAULT_TIMEOUT)

        while True:
            raw = await asyncio.wait_for(reader.readline(), timeout=DEFAULT_TIMEOUT)
            if not raw:
                break

            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith("macaddr_RT,"):
                return _parse_discovered_mac("\n".join(lines))
    except (OSError, TimeoutError, asyncio.TimeoutError, ValueError) as err:
        raise ValueError("unable to discover MAC") from err
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    raise ValueError("unable to discover MAC")


def _data_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Return the user step schema."""
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_MAC3, default=user_input.get(CONF_MAC3, "")): str,
            vol.Optional(CONF_MAC4, default=user_input.get(CONF_MAC4, "")): str,
            vol.Optional(CONF_MAC5, default=user_input.get(CONF_MAC5, "")): str,
            vol.Optional(CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
        }
    )


class ControlartWiredRelayConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Controlart Wired Relay."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            name = str(user_input.get(CONF_NAME, DEFAULT_NAME)).strip() or DEFAULT_NAME
            mac3 = mac4 = mac5 = ""
            port = int(user_input[CONF_PORT])

            if not host:
                errors[CONF_HOST] = "required"

            raw_mac_parts = {
                CONF_MAC3: str(user_input.get(CONF_MAC3, "")).strip(),
                CONF_MAC4: str(user_input.get(CONF_MAC4, "")).strip(),
                CONF_MAC5: str(user_input.get(CONF_MAC5, "")).strip(),
            }
            manual_mac = all(raw_mac_parts.values())

            if manual_mac:
                for field, raw_value in raw_mac_parts.items():
                    try:
                        normalized = _clean_mac_part(raw_value)
                    except (TypeError, ValueError):
                        errors[field] = "invalid_mac_part"
                        continue

                    if field == CONF_MAC3:
                        mac3 = normalized
                    elif field == CONF_MAC4:
                        mac4 = normalized
                    else:
                        mac5 = normalized
            elif not errors:
                try:
                    mac3, mac4, mac5 = await _async_discover_mac(host, port)
                except ValueError:
                    errors["base"] = "cannot_discover_mac"

            if not errors:
                suffix = _mac_suffix(mac3, mac4, mac5)
                await self.async_set_unique_id(f"{DOMAIN}_{suffix}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MAC3: mac3,
                        CONF_MAC4: mac4,
                        CONF_MAC5: mac5,
                        CONF_NAME: name,
                    },
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_data_schema(user_input),
            errors=errors,
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from YAML."""
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return ControlartWiredRelayOptionsFlow(config_entry)


class ControlartWiredRelayOptionsFlow(config_entries.OptionsFlow):
    """Handle Controlart Wired Relay options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            try:
                parse_interlock_pairs(
                    user_input.get(CONF_INTERLOCK_PAIRS, "")
                )
            except (TypeError, ValueError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._options_schema(user_input),
                    errors={CONF_INTERLOCK_PAIRS: "invalid_interlock_pairs"},
                )

            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_INTERLOCK_PAIRS: str(
                        user_input.get(CONF_INTERLOCK_PAIRS, "")
                    ).strip(),
                    CONF_INTERLOCK_DELAY_MS: int(
                        user_input[CONF_INTERLOCK_DELAY_MS]
                    ),
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._options_schema(self._config_entry.options),
        )

    def _options_schema(self, values: dict[str, Any]) -> vol.Schema:
        """Return options schema."""
        current_scan_interval = values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_pairs = values.get(CONF_INTERLOCK_PAIRS, "")
        current_delay = values.get(
            CONF_INTERLOCK_DELAY_MS, DEFAULT_INTERLOCK_DELAY_MS
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_scan_interval
                ): vol.All(
                    int, vol.Range(min=1, max=3600)
                ),
                vol.Required(
                    CONF_INTERLOCK_PAIRS, default=current_pairs
                ): str,
                vol.Required(
                    CONF_INTERLOCK_DELAY_MS, default=current_delay
                ): vol.All(
                    int,
                    vol.Range(
                        min=MIN_INTERLOCK_DELAY_MS,
                        max=MAX_INTERLOCK_DELAY_MS,
                    ),
                ),
            }
        )
        return schema
