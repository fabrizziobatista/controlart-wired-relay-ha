"""The Controlart Wired Relay integration."""

from __future__ import annotations

from datetime import timedelta
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_DURATION_MS,
    CONF_INTERLOCK_DELAY_MS,
    CONF_INTERLOCK_PAIRS,
    CONF_MAC3,
    CONF_MAC4,
    CONF_MAC5,
    CONF_SCAN_INTERVAL,
    DEFAULT_INTERLOCK_DELAY_MS,
    DEFAULT_PULSE_DURATION_MS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_PULSE_DURATION_MS,
    MIN_PULSE_DURATION_MS,
    parse_interlock_pairs,
    PLATFORMS,
    SERVICE_PULSE_OUTPUT,
)
from .coordinator import ControlartRelayClient, ControlartRelayCoordinator

PULSE_OUTPUT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(
            ATTR_DURATION_MS, default=DEFAULT_PULSE_DURATION_MS
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_PULSE_DURATION_MS, max=MAX_PULSE_DURATION_MS),
        ),
    }
)

OUT_UNIQUE_ID_RE = re.compile(r"_out(?P<channel>\d+)$")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML, currently unused."""
    async def async_handle_pulse_output(call) -> None:
        """Handle pulse_output service calls."""
        entity_id = call.data[CONF_ENTITY_ID]
        duration_ms = call.data[ATTR_DURATION_MS]

        entity_entry = er.async_get(hass).async_get(entity_id)
        if (
            entity_entry is None
            or entity_entry.platform != DOMAIN
            or not entity_entry.unique_id
            or entity_entry.config_entry_id is None
        ):
            raise HomeAssistantError(
                f"{entity_id} is not a {DOMAIN} switch entity"
            )

        domain = entity_id.split(".", 1)[0]
        if domain != "switch":
            raise HomeAssistantError(
                f"{entity_id} is not a {DOMAIN} switch entity"
            )

        match = OUT_UNIQUE_ID_RE.search(entity_entry.unique_id)
        if match is None:
            raise HomeAssistantError(
                f"{entity_id} is not a {DOMAIN} output switch"
            )

        coordinator: ControlartRelayCoordinator | None = hass.data.get(
            DOMAIN, {}
        ).get(entity_entry.config_entry_id)
        if coordinator is None:
            raise HomeAssistantError(
                f"No active {DOMAIN} coordinator for {entity_id}"
            )

        await coordinator.async_pulse_output(
            int(match.group("channel")),
            duration_ms,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PULSE_OUTPUT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PULSE_OUTPUT,
            async_handle_pulse_output,
            schema=PULSE_OUTPUT_SCHEMA,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Controlart Wired Relay from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    client = ControlartRelayClient(
        host=entry.data[CONF_HOST],
        port=int(entry.data[CONF_PORT]),
        mac3=entry.data[CONF_MAC3],
        mac4=entry.data[CONF_MAC4],
        mac5=entry.data[CONF_MAC5],
    )
    coordinator = ControlartRelayCoordinator(
        hass=hass,
        client=client,
        name=entry.data[CONF_NAME],
        update_interval=timedelta(seconds=scan_interval),
        interlock_pairs=parse_interlock_pairs(
            entry.options.get(CONF_INTERLOCK_PAIRS, "")
        ),
        interlock_delay_ms=int(
            entry.options.get(
                CONF_INTERLOCK_DELAY_MS,
                DEFAULT_INTERLOCK_DELAY_MS,
            )
        ),
    )
    coordinator.config_entry_id = entry.entry_id

    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_listener(entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: ControlartRelayCoordinator | None = hass.data[DOMAIN].get(
        entry.entry_id
    )
    if coordinator:
        await coordinator.async_stop_listener()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
