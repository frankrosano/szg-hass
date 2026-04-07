"""Sensor entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyszg import ApplianceType, CookMode, WashCycle, WashStatus

from .const import DOMAIN
from .coordinator import SZGCoordinator
from .entity import SZGEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for conn in coordinator.devices.values():
        atype = conn.appliance_type

        if atype == ApplianceType.OVEN:
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav_temp", "Upper Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav2_temp", "Lower Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav_set_temp", "Upper Set Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav2_set_temp", "Lower Set Temperature"))
            entities.append(SZGCookModeSensor(coordinator, conn, "cav_cook_mode", "Upper Cook Mode"))
            entities.append(SZGCookModeSensor(coordinator, conn, "cav2_cook_mode", "Lower Cook Mode"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav_probe_temp", "Upper Probe Temperature"))

        elif atype == ApplianceType.REFRIGERATOR:
            entities.append(SZGTemperatureSensor(coordinator, conn, "ref_set_temp", "Fridge Set Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "frz_set_temp", "Freezer Set Temperature"))
            entities.append(SZGPercentSensor(coordinator, conn, "air_filter_pct_remaining", "Air Filter Remaining"))
            entities.append(SZGPercentSensor(coordinator, conn, "water_filter_pct_remaining", "Water Filter Remaining"))

        elif atype == ApplianceType.DISHWASHER:
            entities.append(SZGWashCycleSensor(coordinator, conn, "wash_cycle", "Wash Cycle"))
            entities.append(SZGWashStatusSensor(coordinator, conn, "wash_status", "Wash Status"))
            entities.append(SZGSensor(coordinator, conn, "wash_cycle_end_time", "Cycle End Time"))

        # Common
        entities.append(SZGSensor(coordinator, conn, "uptime", "Uptime"))

    async_add_entities(entities)


class SZGSensor(SZGEntity, SensorEntity):
    """Generic sensor."""

    def __init__(self, coordinator, connection, prop_key, name):
        super().__init__(coordinator, connection, prop_key)
        self._prop_key = prop_key
        self._attr_name = name

    @property
    def native_value(self):
        val = self.appliance.raw.get(self._prop_key)
        if val is None:
            return getattr(self.appliance, self._prop_key, None)
        return val


class SZGTemperatureSensor(SZGSensor):
    """Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_state_class = SensorStateClass.MEASUREMENT


class SZGPercentSensor(SZGSensor):
    """Percentage sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT


class SZGCookModeSensor(SZGSensor):
    """Cook mode sensor that shows the mode name."""

    @property
    def native_value(self) -> str:
        val = self.appliance.raw.get(self._prop_key, 0)
        try:
            return CookMode(val).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown ({val})"


class SZGWashCycleSensor(SZGSensor):
    """Wash cycle sensor that shows the cycle name."""

    @property
    def native_value(self) -> str:
        val = self.appliance.raw.get(self._prop_key, 0)
        try:
            return WashCycle(val).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown ({val})"


class SZGWashStatusSensor(SZGSensor):
    """Wash status sensor that shows the status name."""

    @property
    def native_value(self) -> str:
        val = self.appliance.raw.get(self._prop_key, 0)
        try:
            return WashStatus(val).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown ({val})"
