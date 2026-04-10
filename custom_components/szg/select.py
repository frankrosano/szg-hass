"""Select entities for Sub-Zero Group integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyszg import ApplianceType, CookMode

from .const import DOMAIN
from .coordinator import SZGCoordinator
from .entity import SZGEntity

_LOGGER = logging.getLogger(__name__)

ICE_MAKER_MODES = ["Off", "Normal", "Max Ice", "Night Ice"]
OPERATING_MODES = ["Normal", "High Use", "Short Vacation", "Long Vacation", "Sabbath"]
COOK_MODES = [m.name.replace("_", " ").title() for m in CookMode if m != CookMode.UNKNOWN]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []

    for conn in coordinator.devices.values():
        if conn.appliance_type == ApplianceType.OVEN:
            entities.append(SZGCookModeSelect(coordinator, conn, "cav_cook_mode", "Upper Cook Mode"))
            entities.append(SZGCookModeSelect(coordinator, conn, "cav2_cook_mode", "Lower Cook Mode"))

        elif conn.appliance_type == ApplianceType.REFRIGERATOR:
            entities.append(SZGIceMakerSelect(coordinator, conn))
            entities.append(SZGOperatingModeSelect(coordinator, conn))

        elif conn.appliance_type == ApplianceType.DISHWASHER:
            entities.append(SZGDelayStartSelect(coordinator, conn))

    async_add_entities(entities)


class SZGIceMakerSelect(SZGEntity, SelectEntity):
    """Select entity for ice maker mode: Off, Normal, Max Ice, Night Ice."""

    _attr_options = ICE_MAKER_MODES
    _attr_icon = "mdi:ice-cream"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "ice_maker_mode")
        self._attr_name = "Ice Maker"

    @property
    def current_option(self) -> str | None:
        ice_on = self.appliance.raw.get("ice_maker_on", False)
        max_ice = self.appliance.raw.get("max_ice_on", False)
        night_ice = self.appliance.raw.get("night_ice_on", False)

        if night_ice:
            return "Night Ice"
        if max_ice:
            return "Max Ice"
        if ice_on:
            return "Normal"
        return "Off"

    async def async_select_option(self, option: str) -> None:
        if option == "Off":
            await self._connection.async_set_property(self.hass, "ice_maker_on", False)
            await self._connection.async_set_property(self.hass, "max_ice_on", False)
            await self._connection.async_set_property(self.hass, "night_ice_on", False)
        elif option == "Normal":
            await self._connection.async_set_property(self.hass, "ice_maker_on", True)
            await self._connection.async_set_property(self.hass, "max_ice_on", False)
            await self._connection.async_set_property(self.hass, "night_ice_on", False)
        elif option == "Max Ice":
            await self._connection.async_set_property(self.hass, "ice_maker_on", True)
            await self._connection.async_set_property(self.hass, "max_ice_on", True)
            await self._connection.async_set_property(self.hass, "night_ice_on", False)
        elif option == "Night Ice":
            await self._connection.async_set_property(self.hass, "ice_maker_on", True)
            await self._connection.async_set_property(self.hass, "max_ice_on", False)
            await self._connection.async_set_property(self.hass, "night_ice_on", True)
        await self.coordinator.async_request_refresh()


class SZGOperatingModeSelect(SZGEntity, SelectEntity):
    """Select entity for operating mode.

    WARNING: Sabbath mode can only be disabled from the appliance's
    physical display. Enabling it remotely will lock out app/remote control.
    """

    _attr_options = OPERATING_MODES
    _attr_icon = "mdi:cog"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "operating_mode")
        self._attr_name = "Operating Mode"

    @property
    def current_option(self) -> str | None:
        sabbath = self.appliance.raw.get("sabbath_on", False)
        high_use = self.appliance.raw.get("high_use_on", False)
        short_vac = self.appliance.raw.get("short_vacation_on", False)
        long_vac = self.appliance.raw.get("long_vacation_on", False)

        if sabbath:
            return "Sabbath"
        if high_use:
            return "High Use"
        if long_vac:
            return "Long Vacation"
        if short_vac:
            return "Short Vacation"
        return "Normal"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {}
        if self.current_option == "Sabbath":
            attrs["warning"] = (
                "Sabbath Mode can only be disabled from the appliance display. "
                "Remote control is locked while Sabbath Mode is active."
            )
        return attrs

    async def async_select_option(self, option: str) -> None:
        if option == "Sabbath":
            _LOGGER.warning(
                "Enabling Sabbath Mode on %s. This can only be disabled "
                "from the appliance's physical display.",
                self._connection.name,
            )

        # Clear all modes first
        await self._connection.async_set_property(self.hass, "sabbath_on", False)
        await self._connection.async_set_property(self.hass, "high_use_on", False)
        await self._connection.async_set_property(self.hass, "short_vacation_on", False)
        await self._connection.async_set_property(self.hass, "long_vacation_on", False)

        # Set the selected mode
        if option == "High Use":
            await self._connection.async_set_property(self.hass, "high_use_on", True)
        elif option == "Short Vacation":
            await self._connection.async_set_property(self.hass, "short_vacation_on", True)
        elif option == "Long Vacation":
            await self._connection.async_set_property(self.hass, "long_vacation_on", True)
        elif option == "Sabbath":
            await self._connection.async_set_property(self.hass, "sabbath_on", True)
        # "Normal" = all off, which we already did

        await self.coordinator.async_request_refresh()


class SZGCookModeSelect(SZGEntity, SelectEntity):
    """Select entity for oven cook mode.

    Setting a cook mode while the oven is running changes the active mode.
    Setting a mode while idle requires Remote Ready to be enabled first.
    Selecting Off turns the cavity off via cav_unit_on.
    """

    _attr_options = COOK_MODES
    _attr_icon = "mdi:stove"

    def __init__(self, coordinator, connection, prop_key, name):
        super().__init__(coordinator, connection, prop_key)
        self._prop_key = prop_key
        # Derive the unit_on key from the cook_mode key (cav_cook_mode -> cav_unit_on)
        self._unit_key = prop_key.replace("cook_mode", "unit_on")
        self._attr_name = name

    @property
    def current_option(self) -> str | None:
        val = self.appliance.raw.get(self._prop_key, 0)
        try:
            return CookMode(val).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown ({val})"

    async def async_select_option(self, option: str) -> None:
        enum_name = option.upper().replace(" ", "_")
        try:
            mode_value = CookMode[enum_name].value
        except KeyError:
            _LOGGER.error("Unknown cook mode: %s", option)
            return

        if mode_value == CookMode.OFF:
            # Turn the cavity off
            await self._connection.async_set_property(
                self.hass, self._unit_key, False
            )
        else:
            await self._connection.async_set_property(
                self.hass, self._prop_key, mode_value
            )
        await self.coordinator.async_request_refresh()


DELAY_START_OPTIONS = ["Off"] + [f"{h} Hour{'s' if h > 1 else ''}" for h in range(1, 13)]


class SZGDelayStartSelect(SZGEntity, SelectEntity):
    """Select entity for dishwasher delay start timer (Off, 1-12 hours)."""

    _attr_options = DELAY_START_OPTIONS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, connection):
        super().__init__(coordinator, connection, "delay_start")
        self._attr_name = "Delay Start"

    @property
    def current_option(self) -> str | None:
        duration = self.appliance.raw.get("delay_start_timer_duration", 0)

        if not duration:
            return "Off"

        hours = int(duration)
        if hours < 1:
            return "Off"
        if hours > 12:
            hours = 12
        return f"{hours} Hour{'s' if hours > 1 else ''}"

    async def async_select_option(self, option: str) -> None:
        if option == "Off":
            await self._connection.async_set_property(
                self.hass, "delay_start_timer_duration", 0
            )
        else:
            hours = int(option.split()[0])
            await self._connection.async_set_property(
                self.hass, "delay_start_timer_duration", hours
            )
        await self.coordinator.async_request_refresh()
