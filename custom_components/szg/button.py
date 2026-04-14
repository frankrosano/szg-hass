"""Button entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up button entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []

    for conn in coordinator.devices.values():
        # Remote start button for ovens and dishwashers
        if conn.appliance_type == ApplianceType.OVEN:
            entities.append(SZGRemoteStartButton(
                coordinator, conn,
                unit_key="cav_unit_on",
                ready_key="cav_remote_ready",
                name="Upper Remote Start",
            ))
            entities.append(SZGRemoteStartButton(
                coordinator, conn,
                unit_key="cav2_unit_on",
                ready_key="cav2_remote_ready",
                name="Lower Remote Start",
            ))
        elif conn.appliance_type == ApplianceType.DISHWASHER:
            entities.append(SZGRemoteStartButton(
                coordinator, conn,
                unit_key="wash_cycle_on",
                ready_key="remote_ready",
                name="Start Wash Cycle",
            ))

    async_add_entities(entities)


class SZGRemoteStartButton(SZGEntity, ButtonEntity):
    """Button to start an appliance when Remote Ready is enabled.

    Only available (pressable) when the appliance is in Remote Ready mode.
    Greyed out / unavailable otherwise.
    """

    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator, connection, unit_key, ready_key, name):
        super().__init__(coordinator, connection, f"remote_start_{unit_key}")
        self._unit_key = unit_key
        self._ready_key = ready_key
        self._attr_name = name

    @property
    def available(self) -> bool:
        """Only available when Remote Ready is enabled."""
        return bool(self.appliance.raw.get(self._ready_key, False))

    async def async_press(self) -> None:
        """Start the appliance."""
        await self._connection.async_set_property(
            self.hass, self._unit_key, True
        )
        await self.coordinator.async_request_refresh()
