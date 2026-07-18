"""Coordinator and TCP client for Controlart Wired Relay."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_TIMEOUT, DOMAIN, EVENT_KEYPAD, INPUT_COUNT, OUTLET_COUNT

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 5
KEYPAD_EVENT_MAP = {
    "0": "click",
    "1": "double_click",
    "2": "long_click",
    "3": "press",
    "4": "release",
}


class ControlartRelayError(Exception):
    """Base error for Controlart relay communication."""


class ControlartRelayData(TypedDict):
    """Controlart relay module state."""

    inputs: list[bool]
    outputs: list[bool]


class ControlartRelayClient:
    """Small async TCP client for the Controlart relay protocol."""

    def __init__(
        self,
        host: str,
        port: int,
        mac3: str,
        mac4: str,
        mac5: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the TCP client."""
        self.host = host
        self.port = port
        self.mac3 = mac3
        self.mac4 = mac4
        self.mac5 = mac5
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def mac_suffix(self) -> str:
        """Return the MAC suffix used by the module protocol."""
        return f"{self.mac3}-{self.mac4}-{self.mac5}"

    @property
    def command_mac_suffix(self) -> str:
        """Return the MAC suffix as decimal values required by mdcmd commands."""
        return ",".join(
            (
                self._hex_to_decimal_string(self.mac3),
                self._hex_to_decimal_string(self.mac4),
                self._hex_to_decimal_string(self.mac5),
            )
        )

    @staticmethod
    def _hex_to_decimal_string(value: str) -> str:
        """Convert one normalized hexadecimal MAC field to decimal text."""
        return str(int(value, 16))

    async def async_get_state(self) -> ControlartRelayData:
        """Fetch current input and output states."""
        response = await self._async_send_command(
            f"mdcmd_getmd,{self.command_mac_suffix}"
        )
        return self._parse_state(response)

    async def async_set_output(
        self, channel: int, value: bool
    ) -> ControlartRelayData:
        """Set one output and return the full module state from the response."""
        if channel < 0 or channel >= OUTLET_COUNT:
            raise ControlartRelayError(f"Invalid output channel: {channel}")

        response = await self._async_send_command(
            "mdcmd_sendrele,"
            f"{self.command_mac_suffix},{channel},{1 if value else 0}"
        )
        return self._parse_state(response)

    async def _async_send_command(self, command: str) -> str:
        """Send one CRLF-terminated command and read lines until setcmd."""
        payload = f"{command}\r\n".encode("ascii")
        lines: list[str] = []

        async with self._lock:
            _LOGGER.debug(
                "Sending Controlart command to %s:%s for %s: %s",
                self.host,
                self.port,
                self.mac_suffix,
                command,
            )
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout,
                )
                self._writers.add(writer)
            except (OSError, TimeoutError, asyncio.TimeoutError) as err:
                raise ControlartRelayError(
                    f"Unable to connect to {self.host}:{self.port}"
                ) from err

            try:
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                lines = await asyncio.wait_for(
                    self._async_read_until_setcmd(reader), timeout=self.timeout
                )
            except (TimeoutError, asyncio.TimeoutError) as err:
                raise ControlartRelayError(
                    "No setcmd response received before timeout"
                ) from err
            except OSError as err:
                raise ControlartRelayError("TCP command failed") from err
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                self._writers.discard(writer)

        response = "\n".join(lines)
        _LOGGER.debug("Controlart response: %s", response)
        return response

    async def async_close(self) -> None:
        """Close every active command connection."""
        writers = tuple(self._writers)
        for writer in writers:
            writer.close()
        for writer in writers:
            with suppress(OSError):
                await writer.wait_closed()
            self._writers.discard(writer)

    async def _async_read_until_setcmd(
        self, reader: asyncio.StreamReader
    ) -> list[str]:
        """Read protocol lines until a line starting with setcmd is found."""
        lines: list[str] = []

        while True:
            raw = await reader.readline()
            if not raw:
                break

            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith("setcmd"):
                return lines

            _LOGGER.debug("Ignoring Controlart line before setcmd: %s", line)

        if lines:
            raise ControlartRelayError(
                "No setcmd response received; ignored lines: "
                f"{', '.join(lines)}"
            )
        raise ControlartRelayError("No setcmd response received")

    def _parse_state(self, response: str) -> ControlartRelayData:
        """Parse IN0..IN11 and OUT0..OUT9 from a setcmd response."""
        setcmd_line = next(
            (
                line.strip()
                for line in response.splitlines()
                if line.strip().startswith("setcmd")
            ),
            "",
        )
        if not setcmd_line:
            raise ControlartRelayError(f"No setcmd response found: {response}")

        parts = [part.strip() for part in setcmd_line.split(",")]
        expected_len = 2 + INPUT_COUNT + OUTLET_COUNT

        if len(parts) != expected_len or parts[0] != "setcmd":
            raise ControlartRelayError(f"Unexpected setcmd response: {setcmd_line}")

        if parts[1].upper() != self.mac_suffix.upper():
            raise ControlartRelayError(
                f"Response MAC {parts[1]} does not match {self.mac_suffix}"
            )

        inputs = parts[2 : 2 + INPUT_COUNT]
        outputs = parts[2 + INPUT_COUNT :]
        if any(input_state not in {"0", "1"} for input_state in inputs):
            raise ControlartRelayError(f"Invalid input states: {inputs}")
        if any(output not in {"0", "1"} for output in outputs):
            raise ControlartRelayError(f"Invalid output states: {outputs}")

        return {
            "inputs": [input_state == "1" for input_state in inputs],
            "outputs": [output == "1" for output in outputs],
        }


class ControlartRelayCoordinator(DataUpdateCoordinator[ControlartRelayData]):
    """Coordinate Controlart relay state updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ControlartRelayClient,
        name: str,
        update_interval: timedelta,
        interlock_pairs: list[tuple[int, int]] | None = None,
        interlock_delay_ms: int = 500,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{name}",
            update_interval=update_interval,
        )
        self.client = client
        self.device_name = name
        self._hass = hass
        self.config_entry_id: str | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._listener_writer: asyncio.StreamWriter | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._pulse_locks: dict[int, asyncio.Lock] = {}
        self._interlock_pairs = interlock_pairs or []
        self._interlock_delay_ms = interlock_delay_ms
        self._interlock_fallback_active: set[tuple[int, int]] = set()
        self.connection_status = "disconnected"
        self.last_update: datetime | None = None
        self.last_error: str | None = None
        _LOGGER.debug(
            "Controlart interlock config for %s: pairs=%s delay_ms=%s",
            self.client.mac_suffix,
            self._interlock_pairs,
            self._interlock_delay_ms,
        )

    def _set_connection_status(self, status: str) -> None:
        """Update connection status diagnostic state."""
        if self.connection_status == status:
            return
        self.connection_status = status
        self.async_update_listeners()

    def _set_last_error(self, error: str | None) -> None:
        """Update last error diagnostic state."""
        if self.last_error == error:
            return
        self.last_error = error
        self.async_update_listeners()

    def _record_valid_update(self) -> None:
        """Record the timestamp of the latest valid setcmd payload."""
        self.last_update = datetime.now(UTC)
        self.last_error = None

    def async_start_listener(self, entry: Any | None = None) -> None:
        """Start the persistent TCP listener as a background task."""
        if self._listener_task and not self._listener_task.done():
            return

        self._set_connection_status("reconnecting")
        name = f"{DOMAIN}_{self.client.mac_suffix}_listener"
        if entry is not None and hasattr(entry, "async_create_background_task"):
            self._listener_task = entry.async_create_background_task(
                self._hass,
                self._async_listen_forever(),
                name,
            )
        else:
            self._listener_task = self._hass.async_create_task(
                self._async_listen_forever(),
                name,
            )

    async def async_stop_listener(self) -> None:
        """Stop the listener, commands, and coordinator-owned tasks."""
        _LOGGER.info(
            "Closing Controlart connection to %s:%s for %s",
            self.client.host,
            self.client.port,
            self.client.mac_suffix,
        )
        writer = self._listener_writer
        if writer:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self._listener_writer = None

        if self._listener_task:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        tasks = tuple(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        await self.client.async_close()
        _LOGGER.info("Controlart connection closed for %s", self.client.mac_suffix)

    async def _async_listen_forever(self) -> None:
        """Keep a TCP listener connected and process async setcmd events."""
        while True:
            writer: asyncio.StreamWriter | None = None
            try:
                _LOGGER.debug(
                    "Connecting Controlart listener to %s:%s for %s",
                    self.client.host,
                    self.client.port,
                    self.client.mac_suffix,
                )
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.client.host, self.client.port),
                    timeout=self.client.timeout,
                )
                self._listener_writer = writer
                self._set_connection_status("connected")
                self._set_last_error(None)
                _LOGGER.debug(
                    "Controlart listener connected to %s:%s for %s",
                    self.client.host,
                    self.client.port,
                    self.client.mac_suffix,
                )

                while True:
                    raw = await reader.readline()
                    if not raw:
                        _LOGGER.warning(
                            "Controlart listener connection closed for %s",
                            self.client.mac_suffix,
                        )
                        self._set_connection_status("disconnected")
                        self._set_last_error("Listener connection closed")
                        break

                    line = raw.decode("ascii", errors="ignore").strip()
                    if not line:
                        continue

                    _LOGGER.debug(
                        "Controlart listener received for %s: %s",
                        self.client.mac_suffix,
                        line,
                    )

                    if line.startswith("setcankpfb"):
                        self._process_keypad_line(line)
                        continue

                    if not line.startswith("setcmd"):
                        _LOGGER.debug(
                            "Ignoring Controlart listener line before setcmd: %s",
                            line,
                        )
                        continue

                    try:
                        data = self.client._parse_state(line)
                    except ControlartRelayError as err:
                        _LOGGER.debug(
                            "Ignoring invalid Controlart setcmd for %s: %s",
                            self.client.mac_suffix,
                            err,
                        )
                        continue

                    _LOGGER.debug(
                        "Processed Controlart setcmd for %s",
                        self.client.mac_suffix,
                    )
                    self._record_valid_update()
                    self.async_set_updated_data(data)
                    self._check_interlock_conflicts(data)
            except asyncio.CancelledError:
                _LOGGER.debug(
                    "Controlart listener cancelled for %s",
                    self.client.mac_suffix,
                )
                raise
            except (OSError, TimeoutError, asyncio.TimeoutError) as err:
                self._set_connection_status("disconnected")
                self._set_last_error(str(err))
                _LOGGER.debug(
                    "Controlart listener connection error for %s: %s",
                    self.client.mac_suffix,
                    err,
                )
            except Exception as err:
                self._set_connection_status("disconnected")
                self._set_last_error(str(err))
                _LOGGER.debug(
                    "Unexpected Controlart listener error for %s: %s",
                    self.client.mac_suffix,
                    err,
                )
            finally:
                if writer:
                    writer.close()
                    with suppress(OSError):
                        await writer.wait_closed()
                if self._listener_writer is writer:
                    self._listener_writer = None

            self._set_connection_status("reconnecting")
            _LOGGER.debug(
                "Reconnecting Controlart listener for %s in %s seconds",
                self.client.mac_suffix,
                RECONNECT_DELAY,
            )
            await asyncio.sleep(RECONNECT_DELAY)

    def _process_keypad_line(self, line: str) -> None:
        """Parse and fire Home Assistant event for a CAN keypad message."""
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            _LOGGER.debug("Ignoring invalid Controlart keypad line: %s", line)
            return

        _, typ_id, dev_id, evt, key = parts
        event_name = KEYPAD_EVENT_MAP.get(evt)
        if event_name is None:
            _LOGGER.debug(
                "Ignoring Controlart keypad line with unknown event %s: %s",
                evt,
                line,
            )
            return

        event_data = {
            "config_entry_id": self.config_entry_id,
            "typ_id": typ_id,
            "dev_id": dev_id,
            "key": key,
            "event": event_name,
            "raw": line,
        }
        _LOGGER.debug("Firing Controlart keypad event: %s", event_data)
        self._hass.bus.async_fire(EVENT_KEYPAD, event_data)

    async def _async_update_data(self) -> ControlartRelayData:
        """Fetch state from the module."""
        try:
            data = await self.client.async_get_state()
        except ControlartRelayError as err:
            self._set_last_error(str(err))
            raise UpdateFailed(str(err)) from err
        self._record_valid_update()
        self._check_interlock_conflicts(data)
        return data

    async def async_set_output(self, channel: int, value: bool) -> None:
        """Set one output and publish returned states optimistically."""
        try:
            if value:
                await self._apply_interlock_before_turn_on(channel)
            states = await self.client.async_set_output(channel, value)
        except ControlartRelayError as err:
            self._set_last_error(str(err))
            raise HomeAssistantError(str(err)) from err

        self._record_valid_update()
        self.async_set_updated_data(states)
        self._check_interlock_conflicts(states)
        await self.async_request_refresh()

    async def async_pulse_output(self, channel: int, duration_ms: int) -> None:
        """Pulse one output for the requested duration."""
        lock = self._pulse_locks.setdefault(channel, asyncio.Lock())
        if lock.locked():
            raise HomeAssistantError(f"Pulse already active for OUT{channel}")

        async with lock:
            await self.async_set_output(channel, True)
            try:
                await asyncio.sleep(duration_ms / 1000)
            finally:
                await self.async_set_output(channel, False)
                await self.async_request_refresh()

    async def _apply_interlock_before_turn_on(self, channel: int) -> None:
        """Turn off paired output before turning this channel on."""
        paired_channel = self._paired_channel(channel)
        if paired_channel is None:
            return

        paired_is_on = bool(
            self.data
            and len(self.data["outputs"]) > paired_channel
            and self.data["outputs"][paired_channel]
        )
        if not paired_is_on:
            return

        _LOGGER.warning(
            "Controlart interlock turning off OUT%s before turning on OUT%s",
            paired_channel,
            channel,
        )
        states = await self.client.async_set_output(paired_channel, False)
        self._record_valid_update()
        self.async_set_updated_data(states)
        await asyncio.sleep(self._interlock_delay_ms / 1000)

    def _paired_channel(self, channel: int) -> int | None:
        """Return configured interlock peer for channel, if any."""
        for first, second in self._interlock_pairs:
            if first == channel:
                return second
            if second == channel:
                return first
        return None

    def _check_interlock_conflicts(self, data: ControlartRelayData) -> None:
        """Detect and correct any configured pair that is simultaneously on."""
        for pair in self._interlock_pairs:
            first, second = pair
            outputs = data["outputs"]
            if (
                len(outputs) <= max(first, second)
                or not outputs[first]
                or not outputs[second]
            ):
                self._interlock_fallback_active.discard(pair)
                continue

            message = (
                f"Interlock conflict detected: OUT{first} and OUT{second} "
                "are both on; turning both off"
            )
            self.last_error = message
            self.async_update_listeners()
            if pair in self._interlock_fallback_active:
                continue

            self._interlock_fallback_active.add(pair)
            _LOGGER.warning("Controlart %s", message)
            task = self._hass.async_create_task(
                self._async_disable_interlock_pair(first, second),
                f"{DOMAIN}_{self.client.mac_suffix}_interlock_{first}_{second}",
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _async_disable_interlock_pair(self, first: int, second: int) -> None:
        """Safely turn off both outputs in a conflicted pair."""
        try:
            await self.client.async_set_output(first, False)
            states = await self.client.async_set_output(second, False)
        except ControlartRelayError as err:
            self._set_last_error(str(err))
            _LOGGER.warning(
                "Controlart interlock failed to turn off OUT%s/OUT%s: %s",
                first,
                second,
                err,
            )
            return

        self.last_update = datetime.now(UTC)
        self.async_set_updated_data(states)
        self._interlock_fallback_active.discard(tuple(sorted((first, second))))

    @property
    def outputs(self) -> Mapping[int, bool]:
        """Return the latest output states keyed by channel."""
        if self.data is None:
            return {}
        return {
            channel: state
            for channel, state in enumerate(self.data["outputs"])
        }

    @property
    def inputs(self) -> Mapping[int, bool]:
        """Return the latest input states keyed by channel."""
        if self.data is None:
            return {}
        return {
            channel: state
            for channel, state in enumerate(self.data["inputs"])
        }
