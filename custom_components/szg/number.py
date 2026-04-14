"""Number entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
    """Set up number entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = []

    for conn in coordinator.devices.values():
        if conn.appliance_type == ApplianceType.OVEN:
            entities.append(
                SZGKitchenTimer(coordinator, conn, "kitchen_timer_duration", "Kitchen Timer 1")
            )
            entities.append(
                SZGKitchenTimer(coordinator, conn, "kitchen_timer2_duration", "Kitchen Timer 2")
            )

        elif conn.appliance_type == ApplianceType.REFRIGERATOR:
            entities.append(
                SZGAccentLight(coordinator, conn)
            )

    async_add_entities(entities)


class SZGKitchenTimer(SZGEntity, NumberEntity):
    """Number entity for setting a kitchen timer duration in minutes.

    Setting a value > 0 starts the timer. Setting 0 cancels it.
    Max 660 minutes (11 hours).
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 660
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, connection, prop_key, name):
        super().__init__(coordinator, connection, prop_key)
        self._prop_key = prop_key
        self._attr_name = name

    @property
    def native_value(self) -> float | None:
        """Return the current timer duration.

        If the timer is active, calculate remaining minutes from end_time.
        If inactive, return 0.
        """
        # Determine which timer this is
        prefix = "kitchen_timer_" if "2" not in self._prop_key else "kitchen_timer2_"
        active = self.appliance.raw.get(f"{prefix}active", False)

        if not active:
            return 0

        end_time = self.appliance.raw.get(f"{prefix}end_time")
        if end_time:
            from datetime import datetime
            try:
                end = datetime.fromisoformat(end_time)
                now = datetime.now(end.tzinfo)
                remaining = (end - now).total_seconds() / 60
                return max(0, round(remaining))
            except (ValueError, TypeError):
                pass

        return 0

    async def async_set_native_value(self, value: float) -> None:
        """Set the timer duration in minutes. 0 cancels the timer."""
        await self._connection.async_set_property(
            self.hass, self._prop_key, int(value)
        )
        await self.coordinator.async_request_refresh()


class SZGAccentLight(SZGEntity, NumberEntity):
    """Accent light level for glass-front refrigerators.

    Disabled by default — only applicable to models with glass front panels.
    """

    _attr_entity_registry_enabled_default = False
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:lightbulb-outline"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "accent_light_level")
        self._attr_name = "Accent Light"

    @property
    def native_value(self) -> float | None:
        val = self.appliance.raw.get("accent_light_level")
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self._connection.async_set_property(
            self.hass, "accent_light_level", int(value)
        )
        await self.coordinator.async_request_refresh()
