"""Base entity for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from pyszg import Appliance

from .const import DOMAIN, MANUFACTURER
from .coordinator import SZGCoordinator, SZGDeviceConnection


class SZGEntity(CoordinatorEntity[SZGCoordinator]):
    """Base entity for a Sub-Zero Group appliance."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SZGCoordinator,
        connection: SZGDeviceConnection,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._connection = connection
        self._attr_unique_id = f"{connection.device_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this entity."""
        conn = self._connection
        appliance = conn.appliance
        info = DeviceInfo(
            identifiers={(DOMAIN, conn.device_id)},
            name=conn.name,
            manufacturer=MANUFACTURER,
            model=appliance.model or conn.device_info.get("applianceId"),
            serial_number=appliance.serial or None,
            sw_version=appliance.fw_version or None,
        )
        return info

    @property
    def appliance(self) -> Appliance:
        """Return the current appliance state."""
        return self._connection.appliance
