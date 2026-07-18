"""Binary sensor platform for Controlart Wired Relay."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    INPUT_COUNT,
    INTEGRATION_VERSION,
    MANUFACTURER,
    MODEL,
)
from .coordinator import ControlartRelayCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Controlart relay input binary sensors from a config entry."""
    coordinator: ControlartRelayCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ControlartRelayInputBinarySensor(coordinator, entry, channel)
        for channel in range(INPUT_COUNT)
    )


class ControlartRelayInputBinarySensor(
    CoordinatorEntity[ControlartRelayCoordinator], BinarySensorEntity
):
    """Representation of one Controlart relay input."""

    def __init__(
        self,
        coordinator: ControlartRelayCoordinator,
        entry: ConfigEntry,
        channel: int,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._channel = channel
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.client.mac3}_{coordinator.client.mac4}_"
            f"{coordinator.client.mac5}_in{channel}"
        )
        self._attr_name = f"{entry.data[CONF_NAME]} IN{channel}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.client.mac_suffix)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self._entry.data[CONF_NAME],
            configuration_url=f"http://{self._current_host}",
            sw_version=f"Integration {INTEGRATION_VERSION}",
        )

    @property
    def _current_host(self) -> str:
        """Return the options host with legacy data fallback."""
        return self._entry.options.get(CONF_HOST, self._entry.data[CONF_HOST])

    @property
    def icon(self) -> str:
        """Return the icon for the current input state."""
        if self.is_on:
            return "mdi:electric-switch-closed"
        return "mdi:electric-switch"

    @property
    def is_on(self) -> bool | None:
        """Return true if the input is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["inputs"][self._channel]
