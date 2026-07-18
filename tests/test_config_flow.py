"""Tests for the Controlart options flow."""

from unittest.mock import AsyncMock, patch

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controlart_wired_relay.const import (
    CONF_INTERLOCK_DELAY_MS,
    CONF_INTERLOCK_PAIRS,
    CONF_MAC3,
    CONF_MAC4,
    CONF_MAC5,
    CONF_SCAN_INTERVAL,
    DEFAULT_INTERLOCK_DELAY_MS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.controlart_wired_relay.coordinator import ControlartRelayError


def _entry(options: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.0.2.10",
            CONF_PORT: 4998,
            CONF_NAME: "Relay",
            CONF_MAC3: "6D",
            CONF_MAC4: "08",
            CONF_MAC5: "CA",
        },
        options=options or {},
        unique_id="controlart_wired_relay_6D_08_CA",
    )


async def test_options_form_uses_data_fallback(hass) -> None:
    """Old entries expose data host/port and option defaults."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"]({})
    assert schema[CONF_HOST] == "192.0.2.10"
    assert schema[CONF_PORT] == 4998
    assert schema[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL

    interlock_marker = next(
        marker
        for marker in result["data_schema"].schema
        if marker.schema == CONF_INTERLOCK_PAIRS
    )
    assert isinstance(interlock_marker, vol.Optional)


async def test_options_accepts_empty_interlock_pairs(hass) -> None:
    """The options flow saves successfully with no interlock pairs."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.controlart_wired_relay.config_flow."
        "ControlartRelayClient.async_get_state",
        AsyncMock(return_value={"inputs": [False] * 12, "outputs": [False] * 10}),
    ):
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "192.0.2.10",
                CONF_PORT: 4998,
                CONF_SCAN_INTERVAL: 5,
                CONF_INTERLOCK_PAIRS: "",
                CONF_INTERLOCK_DELAY_MS: DEFAULT_INTERLOCK_DELAY_MS,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INTERLOCK_PAIRS] == ""


async def test_options_save_host_port_and_reload(hass) -> None:
    """A valid protocol response saves all options and triggers reload."""
    entry = _entry({CONF_SCAN_INTERVAL: 12})
    entry.add_to_hass(hass)
    entry.add_update_listener(
        lambda hass, entry: hass.config_entries.async_reload(entry.entry_id)
    )
    reload_mock = AsyncMock(return_value=True)

    with (
        patch(
            "custom_components.controlart_wired_relay.config_flow."
            "ControlartRelayClient.async_get_state",
            AsyncMock(return_value={"inputs": [False] * 12, "outputs": [False] * 10}),
        ),
        patch.object(hass.config_entries, "async_reload", reload_mock),
    ):
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "relay.example.local",
                CONF_PORT: 5000,
                CONF_SCAN_INTERVAL: 15,
                CONF_INTERLOCK_PAIRS: "0-1",
                CONF_INTERLOCK_DELAY_MS: DEFAULT_INTERLOCK_DELAY_MS,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_HOST] == "relay.example.local"
    assert entry.options[CONF_PORT] == 5000
    reload_mock.assert_awaited_once_with(entry.entry_id)


async def test_options_validation_failure_does_not_save(hass) -> None:
    """An invalid module response keeps the old active options."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.controlart_wired_relay.config_flow."
        "ControlartRelayClient.async_get_state",
        AsyncMock(side_effect=ControlartRelayError("bad response")),
    ):
        flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            flow["flow_id"],
            {
                CONF_HOST: "192.0.2.99",
                CONF_PORT: 5001,
                CONF_SCAN_INTERVAL: 5,
                CONF_INTERLOCK_PAIRS: "",
                CONF_INTERLOCK_DELAY_MS: DEFAULT_INTERLOCK_DELAY_MS,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_response"}
    assert CONF_HOST not in entry.options
