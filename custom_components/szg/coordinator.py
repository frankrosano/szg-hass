"""Data coordinator for Sub-Zero Group integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pyszg import (
    Appliance,
    ApplianceType,
    ModuleGeneration,
    SZGClient,
    SZGCloudAuth,
    SZGCloudClient,
    SZGCloudSignalR,
    TokenSet,
    TokenStore,
)
from pyszg.exceptions import AuthenticationError as PySZGAuthError, SZGError

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

    @property
    def local_push_active(self) -> bool:
        """True iff a local persistent push connection is currently delivering updates.

        Encodes both halves of the condition: the background task must
        still be running AND the underlying TLS stream must be alive.
        """
        return (
            self._local_push_task is not None
            and not self._local_push_task.done()
            and self.local_client is not None
            and self.local_client.is_push_connected
        )

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
        """Refresh appliance state using the best available method.

        Raises ``pyszg.AuthenticationError`` only on *cloud* auth failure
        so the coordinator can surface ``ConfigEntryAuthFailed`` to HA.
        A *local* auth failure (PIN/lockout) is not a cloud-token problem,
        so it falls back to cloud rather than propagating. Other
        ``SZGError`` subtypes (transport, timeout, command) are logged and
        the local-then-cloud fallback continues.
        """
        if self.has_local:
            try:
                await hass.async_add_executor_job(self.local_client.refresh)
                self.appliance = self.local_client.appliance
                return self.appliance
            except PySZGAuthError as exc:
                # A local auth failure is a PIN/lockout problem on the CAT
                # module, NOT a cloud-token problem. Falling through to the
                # cloud path (rather than re-raising) is important: if this
                # propagated, the coordinator would map it to
                # ConfigEntryAuthFailed and trigger a spurious *cloud*
                # reauth flow even though cloud auth is fine.
                _LOGGER.warning(
                    "Local auth failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )
            except SZGError as exc:
                _LOGGER.warning(
                    "Local refresh failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )

        # Cloud fallback (or primary for Saber/NGIX)
        try:
            self.appliance = await hass.async_add_executor_job(
                self.cloud_client.get_appliance_state, self.device_id
            )
        except PySZGAuthError:
            raise
        except SZGError as exc:
            _LOGGER.debug("Cloud refresh failed for %s: %s", self.name, exc)

        return self.appliance

    async def async_set_property(
        self, hass: HomeAssistant, name: str, value: Any
    ) -> None:
        """Set a property using the best available method.

        A local auth failure (PIN/lockout) falls back to cloud rather than
        propagating, since cloud is a separate credential. A cloud auth
        error still propagates so entity service handlers surface a
        meaningful failure rather than silently no-oping.
        """
        if self.has_local:
            try:
                await hass.async_add_executor_job(
                    self.local_client.set_property, name, value
                )
                return
            except PySZGAuthError as exc:
                # Local PIN/lockout failure — fall back to cloud rather
                # than surfacing it as an auth error (cloud auth is a
                # separate credential and is likely still valid).
                _LOGGER.warning(
                    "Local set failed for %s (auth), falling back to cloud: %s",
                    self.name, exc,
                )
            except SZGError as exc:
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
            config_entry=entry,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
            always_update=False,
        )
        self.entry = entry
        self._auth = SZGCloudAuth()
        self._token_store: TokenStore | None = None
        self._cloud_client: SZGCloudClient | None = None
        self._signalr: SZGCloudSignalR | None = None
        self._signalr_task: asyncio.Task | None = None
        self.devices: dict[str, SZGDeviceConnection] = {}

    @property
    def cloud_push_active(self) -> bool:
        """True iff the SignalR WebSocket is currently connected and routing.

        The SignalR access token has a 1-hour lifetime separate from the
        OAuth id_token; once it expires Azure stops routing messages even
        though the WebSocket itself stays open. ``SZGCloudSignalR.is_connected``
        encodes both checks.
        """
        return self._signalr is not None and self._signalr.is_connected

    async def async_setup(self) -> None:
        """Initialize cloud auth and discover devices."""
        token_data = self.entry.data.get(CONF_TOKENS, {})
        initial_tokens = TokenSet.from_dict(token_data)

        # Build the shared token store. The on_refresh callback fires
        # every time pyszg rotates the refresh_token (which Azure AD
        # B2C does on every refresh, invalidating the previous one),
        # so we MUST persist the rotated tokens back to the config
        # entry — otherwise the next HA restart loads an invalidated
        # refresh_token and the integration falls into reauth.
        self._token_store = TokenStore(
            initial_tokens,
            self._auth,
            on_refresh=self._persist_rotated_tokens,
        )

        try:
            await self.hass.async_add_executor_job(self._token_store.get_valid)
        except PySZGAuthError as err:
            raise ConfigEntryAuthFailed("Token refresh failed") from err
        except Exception as err:
            raise ConfigEntryNotReady(f"Cannot connect to Sub-Zero cloud: {err}") from err

        # If the initial refresh rotated, _persist_rotated_tokens already
        # wrote the new tokens. If it didn't (still valid), the entry is
        # already correct.

        self._cloud_client = SZGCloudClient(self._token_store)

        # Discover devices
        try:
            device_list = await self.hass.async_add_executor_job(
                self._cloud_client.get_devices
            )
        except Exception as err:
            raise ConfigEntryNotReady(f"Cannot fetch devices: {err}") from err

        # device_pins live in entry.options after the v1->v2 migration
        # in async_migrate_entry. Both old (data) and new (options)
        # locations are checked so a manually-edited entry with the
        # old layout still works.
        pins = (
            self.entry.options.get(CONF_DEVICE_PINS)
            or self.entry.data.get(CONF_DEVICE_PINS)
            or {}
        )

        for dev_info in device_list:
            device_id = dev_info["id"]
            conn = SZGDeviceConnection(dev_info, self._cloud_client)
            self.devices[device_id] = conn

            # Set up local connection if we have a PIN and the device supports it
            if conn.supports_local and device_id in pins:
                # Get IP from the device info if available, defer cloud fetch
                conn.pin = pins[device_id]

        # (SignalR started separately after setup to avoid blocking bootstrap)

    def _persist_rotated_tokens(self, tokens: TokenSet) -> None:
        """Write rotated tokens back to the config entry.

        Invoked by ``TokenStore`` from whatever thread issued the
        refresh — typically an executor thread doing a cloud REST call
        or SignalR negotiate. We must hop onto the event loop to touch
        ``hass.config_entries`` safely.

        Azure AD B2C rotates the refresh_token on every refresh and
        invalidates the previous one, so persisting promptly is what
        keeps the integration logged in across HA restarts.
        """
        if self.hass.loop.is_closed():
            # HA is shutting down; skip the write.
            return

        token_dict = tokens.to_dict()

        def _do_update() -> None:
            new_data = dict(self.entry.data)
            new_data[CONF_TOKENS] = token_dict
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

        self.hass.loop.call_soon_threadsafe(_do_update)

    async def async_apply_pin_updates(self) -> None:
        """Apply PIN changes from the options flow without restart.

        Checks for new PINs in entry.options (post-migration) and entry.data
        (legacy), and sets up local connections for devices that now have PINs.
        """
        pins = (
            self.entry.options.get(CONF_DEVICE_PINS)
            or self.entry.data.get(CONF_DEVICE_PINS)
            or {}
        )

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

        self._signalr = SZGCloudSignalR(self._token_store)

        device_ids = list(self.devices.keys())

        async def _run_signalr() -> None:
            async def on_signalr_update(device_id: str, msg_type: int, data: dict) -> None:
                if device_id in self.devices:
                    conn = self.devices[device_id]
                    # Skip SignalR updates for devices with active local push
                    if conn.local_push_active:
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
        """Poll all devices for current state (fallback when SignalR misses).

        Per-device refreshes run concurrently. Auth failures from any
        device surface as ``ConfigEntryAuthFailed`` (triggers HA's reauth
        flow); other transport failures surface as ``UpdateFailed``.
        """
        try:
            await asyncio.gather(
                *(conn.async_refresh(self.hass) for conn in self.devices.values())
            )
        except PySZGAuthError as err:
            raise ConfigEntryAuthFailed("Cloud token rejected") from err
        except SZGError as err:
            raise UpdateFailed(str(err)) from err

        # Lazy local connection setup: if we have a PIN but no local client yet,
        # check if the cloud response gave us an IP address.
        for conn in self.devices.values():
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
