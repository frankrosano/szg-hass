"""Data coordinator for Sub-Zero Group integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pyszg import (
    Appliance,
    ApplianceType,
    ModuleGeneration,
    SZGClient,
    SZGCloudAuth,
    SZGCloudClient,
    SZGCloudSignalR,
    TokenSet,
)

from .const import DOMAIN, CONF_TOKENS, CONF_DEVICE_PINS

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(minutes=5)


class SZGDeviceConnection:
    """Manages the connection to a single appliance."""

    def __init__(
        self,
        device_info: dict[str, Any],
        cloud_client: SZGCloudClient,
    ) -> None:
        self.device_id: str = device_info["id"]
        self.device_info = device_info
        self.cloud_client = cloud_client
        self.local_client: SZGClient | None = None
        self.appliance = Appliance()
        self.pin: str | None = None
        self._local_push_task: asyncio.Task | None = None

        # Parse type info from the device list
        type_str = device_info.get("applianceId", "")
        self.appliance_type = ApplianceType.from_type_string(type_str)
        self.module_generation = ModuleGeneration.from_type_string(type_str)

    @property
    def name(self) -> str:
        return (
            self.device_info.get("name")
            or self.appliance.model
            or self.device_info.get("applianceId", "Unknown")
        )

    @property
    def supports_local(self) -> bool:
        return self.module_generation.supports_local_ip

    @property
    def has_local(self) -> bool:
        return self.local_client is not None

    def setup_local(self, ip: str, pin: str) -> None:
        """Set up local IP connection for a CAT device."""
        self.pin = pin
        self.local_client = SZGClient(ip, pin=pin)
        self._local_push_task: asyncio.Task | None = None
        _LOGGER.info("Local connection configured for %s at %s", self.name, ip)

    def start_local_push(
        self, hass: HomeAssistant, on_update: Callable
    ) -> None:
        """Start local push listener in the background."""
        if not self.has_local or self._local_push_task is not None:
            return

        async def _run_local_push() -> None:
            while True:
                try:
                    # Connect push (blocking) in executor
                    await hass.async_add_executor_job(
                        self.local_client.connect_push
                    )
                    _LOGGER.info("Local push connected for %s", self.name)

                    # Read updates in a loop (blocking reads in executor).
                    # The CAT module only sends data when state changes —
                    # an idle appliance sends nothing, which is normal.
                    # Dead sockets are detected by TCP keepalive (raises
                    # OSError) rather than by silence timeout.
                    while True:
                        update = await hass.async_add_executor_job(
                            self.local_client.read_update, 60.0
                        )
                        if update and "props" in update:
                            self.appliance.update_from_response(update["props"])
                            on_update()
                except Exception as exc:
                    _LOGGER.warning(
                        "Local push lost for %s: %s. Reconnecting in 5s...",
                        self.name, exc,
                    )
                    try:
                        self.local_client.disconnect_push()
                    except Exception:
                        pass
                    await asyncio.sleep(5)

        self._local_push_task = hass.async_create_background_task(
            _run_local_push(), f"szg_local_push_{self.device_id[:8]}"
        )

    def stop_local_push(self) -> None:
        """Stop local push listener."""
        if self._local_push_task:
            self._local_push_task.cancel()
            self._local_push_task = None
        if self.local_client:
            self.local_client.disconnect_push()

    async def async_refresh(self, hass: HomeAssistant) -> Appliance:
        """Refresh appliance state using the best available method."""
        if self.has_local:
            try:
                await hass.async_add_executor_job(self.local_client.refresh)
                self.appliance = self.local_client.appliance
                return self.appliance
            except Exception as exc:
                _LOGGER.warning(
                    "Local refresh failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )

        # Cloud fallback (or primary for Saber/NGIX)
        try:
            self.appliance = await hass.async_add_executor_job(
                self.cloud_client.get_appliance_state, self.device_id
            )
        except Exception as exc:
            _LOGGER.debug("Cloud refresh failed for %s: %s", self.name, exc)

        return self.appliance

    async def async_set_property(
        self, hass: HomeAssistant, name: str, value: Any
    ) -> None:
        """Set a property using the best available method."""
        if self.has_local:
            try:
                await hass.async_add_executor_job(
                    self.local_client.set_property, name, value
                )
                return
            except Exception as exc:
                _LOGGER.warning(
                    "Local set failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )

        await hass.async_add_executor_job(
            self.cloud_client.set_property, self.device_id, name, value
        )

    async def async_display_pin(self, hass: HomeAssistant) -> None:
        """Request the appliance to display its PIN."""
        if self.has_local:
            await hass.async_add_executor_job(self.local_client.display_pin)
        else:
            # Use cloud to send display_pin command
            await hass.async_add_executor_job(
                self.cloud_client.send_command,
                self.device_id,
                "display_pin",
                {"duration": 20},
            )


class SZGCoordinator(DataUpdateCoordinator[dict[str, Appliance]]):
    """Coordinate data updates for all Sub-Zero Group appliances."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.entry = entry
        self._auth = SZGCloudAuth()
        self._tokens: TokenSet | None = None
        self._cloud_client: SZGCloudClient | None = None
        self._signalr: SZGCloudSignalR | None = None
        self._signalr_task: asyncio.Task | None = None
        self.devices: dict[str, SZGDeviceConnection] = {}

    async def async_setup(self) -> None:
        """Initialize cloud auth and discover devices."""
        from pyszg.exceptions import AuthenticationError as PySZGAuthError

        token_data = self.entry.data.get(CONF_TOKENS, {})
        self._tokens = TokenSet.from_dict(token_data)

        try:
            self._tokens = await self.hass.async_add_executor_job(
                self._auth.ensure_valid, self._tokens
            )
        except PySZGAuthError as err:
            from homeassistant.exceptions import ConfigEntryAuthFailed
            raise ConfigEntryAuthFailed("Token refresh failed") from err
        except Exception as err:
            from homeassistant.exceptions import ConfigEntryNotReady
            raise ConfigEntryNotReady(f"Cannot connect to Sub-Zero cloud: {err}") from err

        # Save refreshed tokens
        new_data = dict(self.entry.data)
        new_data[CONF_TOKENS] = self._tokens.to_dict()
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

        self._cloud_client = await self.hass.async_add_executor_job(
            SZGCloudClient, self._tokens, self._auth
        )

        # Discover devices
        try:
            device_list = await self.hass.async_add_executor_job(
                self._cloud_client.get_devices
            )
        except Exception as err:
            from homeassistant.exceptions import ConfigEntryNotReady
            raise ConfigEntryNotReady(f"Cannot fetch devices: {err}") from err

        pins = self.entry.data.get(CONF_DEVICE_PINS, {})

        for dev_info in device_list:
            device_id = dev_info["id"]
            conn = SZGDeviceConnection(dev_info, self._cloud_client)
            self.devices[device_id] = conn

            # Set up local connection if we have a PIN and the device supports it
            if conn.supports_local and device_id in pins:
                # Get IP from the device info if available, defer cloud fetch
                conn.pin = pins[device_id]

        # (SignalR started separately after setup to avoid blocking bootstrap)

    async def async_apply_pin_updates(self) -> None:
        """Apply PIN changes from the options flow without restart.

        Checks for new PINs in the config entry data and sets up
        local connections for devices that now have PINs.
        """
        pins = self.entry.data.get(CONF_DEVICE_PINS, {})

        for device_id, conn in self.devices.items():
            if conn.supports_local and device_id in pins and not conn.has_local:
                pin = pins[device_id]
                conn.pin = pin

                # Get IP from the current appliance state or fetch it
                ip = conn.appliance.ip_address
                if not ip:
                    try:
                        appliance = await self.hass.async_add_executor_job(
                            self._cloud_client.get_appliance_state, device_id
                        )
                        ip = appliance.ip_address
                    except Exception as exc:
                        _LOGGER.warning("Failed to get IP for %s: %s", device_id, exc)

                if ip:
                    conn.setup_local(ip, pin)
                    _LOGGER.info(
                        "Local control enabled for %s at %s", conn.name, ip
                    )
                    # Start local push for this device
                    conn.start_local_push(self.hass, self._trigger_update)

    def start_signalr_background(self) -> None:
        """Start SignalR in the background. Call after HA is fully started."""
        if SZGCloudSignalR is None:
            _LOGGER.info("websockets not installed, using polling only")
            return

        if self._signalr_task is not None:
            return  # Already running

        self._signalr = SZGCloudSignalR(self._tokens, self._auth)

        device_ids = list(self.devices.keys())

        async def _run_signalr() -> None:
            async def on_signalr_update(device_id: str, msg_type: int, data: dict) -> None:
                if device_id in self.devices:
                    conn = self.devices[device_id]
                    # Skip SignalR updates for devices with active local push
                    if conn.has_local and conn._local_push_task and not conn._local_push_task.done():
                        return
                    if msg_type == 1:
                        conn.appliance.update_from_response(data)
                    elif msg_type == 2:
                        props = data.get("props", data)
                        conn.appliance.update_from_response(props)
                    self.async_set_updated_data(
                        {did: c.appliance for did, c in self.devices.items()}
                    )

            await self._signalr.connect(
                device_ids=device_ids,
                callback=on_signalr_update,
            )

        self._signalr_task = self.hass.async_create_background_task(
            _run_signalr(), "szg_signalr"
        )

    def _trigger_update(self) -> None:
        """Trigger a coordinator data update from a local push callback."""
        self.async_set_updated_data(
            {did: c.appliance for did, c in self.devices.items()}
        )

    async def _async_update_data(self) -> dict[str, Appliance]:
        """Poll all devices for current state (fallback when SignalR misses)."""
        for conn in self.devices.values():
            await conn.async_refresh(self.hass)

            # Lazy local connection setup: if we have a PIN but no local client yet,
            # check if the cloud response gave us an IP address
            if conn.pin and not conn.has_local and conn.supports_local:
                ip = conn.appliance.ip_address
                if ip:
                    conn.setup_local(ip, conn.pin)
                    conn.start_local_push(self.hass, self._trigger_update)

        return {did: conn.appliance for did, conn in self.devices.items()}

    async def async_shutdown(self) -> None:
        """Clean up connections."""
        if self._signalr:
            await self._signalr.disconnect()
        if self._signalr_task:
            self._signalr_task.cancel()
        for conn in self.devices.values():
            conn.stop_local_push()
            if conn.local_client:
                conn.local_client.disconnect_push()
