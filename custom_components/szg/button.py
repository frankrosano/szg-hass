"""Button entities for Sub-Zero Group integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        # Show PIN button for all CAT devices (enables local control setup)
        if conn.supports_local:
            entities.append(SZGShowPinButton(coordinator, conn))

    async_add_entities(entities)


class SZGShowPinButton(SZGEntity, ButtonEntity):
    """Button to request the appliance to display its PIN.

    A door on the appliance must be physically open for this to work.
    The 6-digit PIN will appear on the appliance's display for 20 seconds.
    """

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "show_pin")
        self._attr_name = "Show PIN"
        self._attr_icon = "mdi:lock-open-variant"

    async def async_press(self) -> None:
        """Request the appliance to display its PIN."""
        await self._connection.async_display_pin(self.hass)
