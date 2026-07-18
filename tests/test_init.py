"""Tests for integration setup, unload, and services."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controlart_wired_relay import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.controlart_wired_relay.const import (
    CONF_MAC3,
    CONF_MAC4,
    CONF_MAC5,
    DOMAIN,
    SERVICE_RELOAD_CONNECTION,
)


def _entry(
    host: str, unique: str, options: dict | None = None
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: host,
            CONF_PORT: 4998,
            CONF_NAME: unique,
            CONF_MAC3: "6D",
            CONF_MAC4: "08",
            CONF_MAC5: unique[-2:],
        },
        options=options or {},
        unique_id=unique,
    )


async def test_setup_uses_options_and_unload_closes_old_connection(hass) -> None:
    """Options override legacy data and unload stops the old coordinator."""
    entry = _entry(
        "192.0.2.10",
        "relay_CA",
        {CONF_HOST: "192.0.2.20", CONF_PORT: 5000},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.controlart_wired_relay.ControlartRelayCoordinator."
            "async_config_entry_first_refresh",
            AsyncMock(),
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.controlart_wired_relay.ControlartRelayCoordinator."
            "async_start_listener"
        ),
    ):
        assert await async_setup_entry(hass, entry)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.client.host == "192.0.2.20"
        assert coordinator.client.port == 5000
        coordinator.async_stop_listener = AsyncMock()
        assert await async_unload_entry(hass, entry)

    coordinator.async_stop_listener.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_reload_service_registered_once_and_targets_selected_entry(hass) -> None:
    """One shared service reloads only the selected device entry."""
    first = _entry("192.0.2.10", "relay_CA")
    second = _entry("192.0.2.11", "relay_CB")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    registry = dr.async_get(hass)
    first_device = registry.async_get_or_create(
        config_entry_id=first.entry_id,
        identifiers={(DOMAIN, "6D-08-CA")},
    )

    assert await async_setup(hass, {})
    assert await async_setup(hass, {})
    assert hass.services.has_service(DOMAIN, SERVICE_RELOAD_CONNECTION)

    reload_mock = AsyncMock(return_value=True)
    with patch.object(hass.config_entries, "async_reload", reload_mock):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RELOAD_CONNECTION,
            {CONF_DEVICE_ID: first_device.id},
            blocking=True,
        )

    reload_mock.assert_awaited_once_with(first.entry_id)
