"""Sensor platform for Controlart Wired Relay diagnostics."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
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
    """Set up Controlart relay diagnostic sensors from a config entry."""
    coordinator: ControlartRelayCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        (
            ControlartConnectionStatusSensor(coordinator, entry),
            ControlartLastUpdateSensor(coordinator, entry),
            ControlartLastErrorSensor(coordinator, entry),
        )
    )


class ControlartDiagnosticSensor(
    CoordinatorEntity[ControlartRelayCoordinator], SensorEntity
):
    """Base class for Controlart diagnostic sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: ControlartRelayCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.client.mac3}_{coordinator.client.mac4}_"
            f"{coordinator.client.mac5}_{key}"
        )
        self._attr_name = f"{entry.data[CONF_NAME]} {name}"

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


class ControlartConnectionStatusSensor(ControlartDiagnosticSensor):
    """Connection status diagnostic sensor."""

    def __init__(
        self, coordinator: ControlartRelayCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the connection status sensor."""
        super().__init__(coordinator, entry, "connection_status", "Connection Status")

    @property
    def native_value(self) -> str:
        """Return current connection status."""
        return self.coordinator.connection_status

    @property
    def icon(self) -> str:
        """Return connection status icon."""
        if self.coordinator.connection_status == "connected":
            return "mdi:lan-connect"
        return "mdi:lan-disconnect"


class ControlartLastUpdateSensor(ControlartDiagnosticSensor):
    """Last valid setcmd timestamp diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: ControlartRelayCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the last update sensor."""
        super().__init__(coordinator, entry, "last_update", "Last Update")

    @property
    def native_value(self) -> datetime | None:
        """Return timestamp of the latest valid setcmd payload."""
        return self.coordinator.last_update


class ControlartLastErrorSensor(ControlartDiagnosticSensor):
    """Last error diagnostic sensor."""

    def __init__(
        self, coordinator: ControlartRelayCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the last error sensor."""
        super().__init__(coordinator, entry, "last_error", "Last Error")

    @property
    def native_value(self) -> str | None:
        """Return latest error text."""
        return self.coordinator.last_error
