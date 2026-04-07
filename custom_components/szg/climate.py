"""Climate entities for Sub-Zero Group integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyszg import ApplianceType, TEMP_RANGE_FRIDGE, TEMP_RANGE_FREEZER

from .const import DOMAIN
from .coordinator import SZGCoordinator
from .entity import SZGEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for refrigeration zones."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ClimateEntity] = []

    for conn in coordinator.devices.values():
        if conn.appliance_type == ApplianceType.REFRIGERATOR:
            entities.append(
                SZGClimate(
                    coordinator, conn,
                    set_key="ref_set_temp",
                    display_key="ref_display_temp",
                    name="Refrigerator",
                    temp_range=TEMP_RANGE_FRIDGE,
                )
            )
            entities.append(
                SZGClimate(
                    coordinator, conn,
                    set_key="frz_set_temp",
                    display_key="frz_display_temp",
                    name="Freezer",
                    temp_range=TEMP_RANGE_FREEZER,
                )
            )

    async_add_entities(entities)


class SZGClimate(SZGEntity, ClimateEntity):
    """Climate entity for a refrigeration zone."""

    _attr_hvac_modes = [HVACMode.COOL]
    _attr_hvac_mode = HVACMode.COOL
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator: SZGCoordinator,
        connection,
        set_key: str,
        display_key: str,
        name: str,
        temp_range: tuple[int, int],
    ) -> None:
        super().__init__(coordinator, connection, set_key)
        self._set_key = set_key
        self._display_key = display_key
        self._attr_name = name
        self._attr_min_temp = float(temp_range[0])
        self._attr_max_temp = float(temp_range[1])
        self._attr_target_temperature_step = 1.0

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature (if available)."""
        val = self.appliance.raw.get(self._display_key)
        return float(val) if val is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        val = self.appliance.raw.get(self._set_key)
        return float(val) if val is not None else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temp = kwargs.get("temperature")
        if temp is not None:
            await self._connection.async_set_property(
                self.hass, self._set_key, int(temp)
            )
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Refrigeration is always cooling — no mode changes."""
        pass
