"""Binary sensor entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyszg import ApplianceType

from .const import DOMAIN
from .coordinator import SZGCoordinator
from .entity import SZGEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []

    for conn in coordinator.devices.values():
        atype = conn.appliance_type

        if atype == ApplianceType.OVEN:
            entities.append(SZGDoorSensor(coordinator, conn, "cav_door_ajar", "Upper Door"))
            entities.append(SZGDoorSensor(coordinator, conn, "cav2_door_ajar", "Lower Door"))
            entities.append(SZGBinarySensor(coordinator, conn, "cav_unit_on", "Upper Cavity Active"))
            entities.append(SZGBinarySensor(coordinator, conn, "cav2_unit_on", "Lower Cavity Active"))
            entities.append(SZGBinarySensor(coordinator, conn, "cav_probe_on", "Upper Probe In Use"))
            entities.append(SZGBinarySensor(coordinator, conn, "cav_remote_ready", "Upper Remote Ready"))
            entities.append(SZGBinarySensor(coordinator, conn, "cav2_remote_ready", "Lower Remote Ready"))

        elif atype == ApplianceType.REFRIGERATOR:
            entities.append(SZGDoorSensor(coordinator, conn, "ref_door_ajar", "Fridge Door"))
            entities.append(SZGDoorSensor(coordinator, conn, "frz_door_ajar", "Freezer Door"))
            entities.append(SZGBinarySensor(coordinator, conn, "service_required", "Service Required", BinarySensorDeviceClass.PROBLEM))

        elif atype == ApplianceType.DISHWASHER:
            entities.append(SZGDoorSensor(coordinator, conn, "door_ajar", "Door"))
            entities.append(SZGBinarySensor(coordinator, conn, "wash_cycle_on", "Wash Cycle Active", BinarySensorDeviceClass.RUNNING))
            entities.append(SZGBinarySensor(coordinator, conn, "remote_ready", "Remote Ready"))
            entities.append(SZGBinarySensor(coordinator, conn, "rinse_aid_low", "Rinse Aid Low", BinarySensorDeviceClass.PROBLEM))
            entities.append(SZGBinarySensor(coordinator, conn, "softener_low", "Softener Low", BinarySensorDeviceClass.PROBLEM))

    async_add_entities(entities)


class SZGBinarySensor(SZGEntity, BinarySensorEntity):
    """Generic binary sensor for a Sub-Zero Group appliance."""

    def __init__(self, coordinator, connection, prop_key, name, device_class=None):
        super().__init__(coordinator, connection, prop_key)
        self._prop_key = prop_key
        self._attr_name = name
        if device_class:
            self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        val = self.appliance.raw.get(self._prop_key)
        if val is None:
            return getattr(self.appliance, self._prop_key, None)
        return bool(val)


class SZGDoorSensor(SZGBinarySensor):
    """Door sensor with appropriate device class."""

    def __init__(self, coordinator, connection, prop_key, name):
        super().__init__(coordinator, connection, prop_key, name, BinarySensorDeviceClass.DOOR)
