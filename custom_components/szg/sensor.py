"""Sensor entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyszg import ApplianceType, WashCycle, WashStatus

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
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav_probe_temp", "Upper Probe Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "cav2_probe_temp", "Lower Probe Temperature"))
            # Cook timers
            entities.append(SZGSensor(coordinator, conn, "cav_cook_timer_end_time", "Upper Cook Timer End"))
            entities.append(SZGSensor(coordinator, conn, "cav2_cook_timer_end_time", "Lower Cook Timer End"))
            # Kitchen timers
            entities.append(SZGSensor(coordinator, conn, "kitchen_timer_end_time", "Kitchen Timer 1 End"))
            entities.append(SZGSensor(coordinator, conn, "kitchen_timer2_end_time", "Kitchen Timer 2 End"))

        elif atype == ApplianceType.REFRIGERATOR:
            entities.append(SZGTemperatureSensor(coordinator, conn, "ref_set_temp", "Fridge Set Temperature"))
            entities.append(SZGTemperatureSensor(coordinator, conn, "frz_set_temp", "Freezer Set Temperature"))
            entities.append(SZGPercentSensor(coordinator, conn, "air_filter_pct_remaining", "Air Filter Remaining"))
            entities.append(SZGPercentSensor(coordinator, conn, "water_filter_pct_remaining", "Water Filter Remaining"))
            entities.append(SZGSensor(coordinator, conn, "water_filter_gal_remaining", "Water Filter Gallons Remaining"))
            entities.append(SZGSensor(coordinator, conn, "max_ice_start_time", "Max Ice Start Time"))
            entities.append(SZGSensor(coordinator, conn, "max_ice_end_time", "Max Ice End Time"))
            entities.append(SZGSensor(coordinator, conn, "high_use_start_time", "High Use Start Time"))
            entities.append(SZGSensor(coordinator, conn, "high_use_end_time", "High Use End Time"))

        elif atype == ApplianceType.DISHWASHER:
            entities.append(SZGWashCycleSensor(coordinator, conn))
            entities.append(SZGWashStatusSensor(coordinator, conn))
            entities.append(SZGSensor(coordinator, conn, "wash_cycle_end_time", "Cycle End Time"))

        # Common (disabled by default)
        entities.append(SZGDiagnosticSensor(coordinator, conn, "uptime", "Uptime"))
        entities.append(SZGDiagnosticSensor(coordinator, conn, "ipv4_addr", "IP Address"))
        entities.append(SZGDiagnosticSensor(coordinator, conn, "device_wlan_id", "MAC Address"))

        # Connection mode diagnostics (enabled by default)
        entities.append(SZGConnectionModeSensor(coordinator, conn))
        entities.append(SZGLiveReportingModeSensor(coordinator, conn))

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


class SZGWashCycleSensor(SZGEntity, SensorEntity):
    """Wash cycle sensor that exposes the cycle as a translated enum.

    Options match the ``WashCycle`` IntEnum names lowercased; an
    ``unknown`` option covers cycle codes the library doesn't yet model.
    Translations live under ``entity.sensor.wash_cycle.*``.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [m.name.lower() for m in WashCycle] + ["unknown"]
    _attr_translation_key = "wash_cycle"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "wash_cycle")

    @property
    def native_value(self) -> str:
        val = self.appliance.raw.get("wash_cycle", 0)
        try:
            return WashCycle(val).name.lower()
        except ValueError:
            return "unknown"


class SZGWashStatusSensor(SZGEntity, SensorEntity):
    """Wash status sensor that exposes the status as a translated enum.

    Options match the ``WashStatus`` IntEnum names lowercased; an
    ``unknown`` option covers status codes the library doesn't yet model.
    Translations live under ``entity.sensor.wash_status.*``.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [m.name.lower() for m in WashStatus] + ["unknown"]
    _attr_translation_key = "wash_status"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "wash_status")

    @property
    def native_value(self) -> str:
        val = self.appliance.raw.get("wash_status", 0)
        try:
            return WashStatus(val).name.lower()
        except ValueError:
            return "unknown"

class SZGDiagnosticSensor(SZGSensor):
    """Diagnostic sensor — disabled by default."""

    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC


class SZGConnectionModeSensor(SZGEntity, SensorEntity):
    """Diagnostic sensor showing the current control connection mode."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["local", "cloud"]
    _attr_translation_key = "connection_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:connection"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "connection_mode")

    @property
    def native_value(self) -> str:
        return "local" if self._connection.has_local else "cloud"


class SZGLiveReportingModeSensor(SZGEntity, SensorEntity):
    """Diagnostic sensor showing the current live reporting connection mode."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["local_push", "cloud_push", "cloud_polling"]
    _attr_translation_key = "live_reporting_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:broadcast"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "live_reporting_mode")

    @property
    def native_value(self) -> str:
        if self._connection.local_push_active:
            return "local_push"
        if self.coordinator.cloud_push_active:
            return "cloud_push"
        return "cloud_polling"
