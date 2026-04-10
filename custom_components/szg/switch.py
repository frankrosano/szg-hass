"""Switch entities for Sub-Zero Group integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []

    for conn in coordinator.devices.values():
        atype = conn.appliance_type

        if atype == ApplianceType.OVEN:
            entities.append(SZGSwitch(coordinator, conn, "cav_light_on", "Upper Light"))
            entities.append(SZGSwitch(coordinator, conn, "cav2_light_on", "Lower Light"))

        elif atype == ApplianceType.REFRIGERATOR:
            pass  # Operating modes and ice maker handled by select entities

        elif atype == ApplianceType.DISHWASHER:
            entities.append(SZGSwitch(coordinator, conn, "heated_dry_on", "Heated Dry"))
            entities.append(SZGSwitch(coordinator, conn, "extended_dry_on", "Extended Dry"))
            entities.append(SZGSwitch(coordinator, conn, "high_temp_wash_on", "High Temp Wash"))
            entities.append(SZGSwitch(coordinator, conn, "sani_rinse_on", "Sani Rinse"))
            entities.append(SZGSwitch(coordinator, conn, "top_rack_only_on", "Top Rack Only"))

    async_add_entities(entities)


class SZGSwitch(SZGEntity, SwitchEntity):
    """Switch entity for a boolean appliance property."""

    def __init__(self, coordinator, connection, prop_key, name):
        super().__init__(coordinator, connection, prop_key)
        self._prop_key = prop_key
        self._attr_name = name

    @property
    def is_on(self) -> bool | None:
        val = self.appliance.raw.get(self._prop_key)
        if val is None:
            return getattr(self.appliance, self._prop_key, None)
        return bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._connection.async_set_property(self.hass, self._prop_key, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._connection.async_set_property(self.hass, self._prop_key, False)
        await self.coordinator.async_request_refresh()
