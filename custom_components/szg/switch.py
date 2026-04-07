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
            entities.append(SZGSwitch(coordinator, conn, "cav_unit_on", "Upper Cavity"))
            entities.append(SZGSwitch(coordinator, conn, "cav2_unit_on", "Lower Cavity"))

        elif atype == ApplianceType.REFRIGERATOR:
            entities.append(SZGSwitch(coordinator, conn, "ice_maker_on", "Ice Maker"))
            entities.append(SZGSwitch(coordinator, conn, "max_ice_on", "Max Ice"))
            entities.append(SZGSwitch(coordinator, conn, "night_ice_on", "Night Ice"))
            entities.append(SZGSwitch(coordinator, conn, "short_vacation_on", "Short Vacation"))
            entities.append(SZGSwitch(coordinator, conn, "long_vacation_on", "Long Vacation"))
            entities.append(SZGSwitch(coordinator, conn, "sabbath_on", "Sabbath Mode"))

        elif atype == ApplianceType.DISHWASHER:
            entities.append(SZGSwitch(coordinator, conn, "heated_dry_on", "Heated Dry"))
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
