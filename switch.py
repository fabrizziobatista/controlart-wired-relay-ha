"""Switch platform for Controlart Wired Relay."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    INTEGRATION_VERSION,
    MANUFACTURER,
    MODEL,
    OUTLET_COUNT,
)
from .coordinator import ControlartRelayCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Controlart relay switches from a config entry."""
    coordinator: ControlartRelayCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ControlartRelaySwitch(coordinator, entry, channel)
        for channel in range(OUTLET_COUNT)
    )


class ControlartRelaySwitch(CoordinatorEntity[ControlartRelayCoordinator], SwitchEntity):
    """Representation of one Controlart relay output."""

    _attr_icon = "mdi:electric-switch"

    def __init__(
        self,
        coordinator: ControlartRelayCoordinator,
        entry: ConfigEntry,
        channel: int,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._channel = channel
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.client.mac3}_{coordinator.client.mac4}_"
            f"{coordinator.client.mac5}_out{channel}"
        )
        self._attr_name = f"{entry.data[CONF_NAME]} OUT{channel}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.client.mac_suffix)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self._entry.data[CONF_NAME],
            configuration_url=f"http://{self._entry.data[CONF_HOST]}",
            sw_version=f"Integration {INTEGRATION_VERSION}",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the output is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["outputs"][self._channel]

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the output on."""
        await self.coordinator.async_set_output(self._channel, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the output off."""
        await self.coordinator.async_set_output(self._channel, False)
