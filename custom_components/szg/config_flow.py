"""Config flow for Sub-Zero Group integration."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from pyszg import SZGClient, SZGCloudAuth, TokenSet
from pyszg.exceptions import AuthenticationError as PySZGAuthError

from .const import DOMAIN, CONF_TOKENS, CONF_DEVICE_PINS

_LOGGER = logging.getLogger(__name__)


class SZGConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sub-Zero Group."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._auth = SZGCloudAuth()
        self._code_verifier: str = ""
        self._reauth_entry: ConfigEntry | None = None

    # --- Shared helpers --------------------------------------------------

    def _show_login_form(
        self,
        step_id: str,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        """Render the auth_url + redirect_url form for both user and reauth steps."""
        # Generate fresh PKCE values each time the form is shown so that
        # if the user takes too long the previous challenge is discarded
        # cleanly and a retry starts a fresh flow.
        self._code_verifier = secrets.token_urlsafe(64)[:128]
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self._code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        state = secrets.token_urlsafe(32)
        auth_url = SZGCloudAuth.get_authorize_url(code_challenge, state)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({
                vol.Required("redirect_url"): str,
            }),
            description_placeholders={"auth_url": auth_url},
            errors=errors or {},
        )

    async def _exchange_redirect_url(
        self, redirect_url: str
    ) -> tuple[TokenSet | None, str | None]:
        """Parse a redirect URL and exchange the embedded code for tokens.

        Returns ``(tokens, None)`` on success, ``(None, error_key)`` on
        failure where ``error_key`` matches a key in strings.json.
        """
        # Extract the auth code from the redirect URL's query string.
        code: str | None = None
        if "?" in redirect_url:
            qs = redirect_url.split("?", 1)[1]
            params = urllib.parse.parse_qs(qs)
            if "code" in params:
                code = params["code"][0]

        if not code:
            return None, "invalid_url"

        try:
            tokens = await self.hass.async_add_executor_job(
                self._auth.exchange_code, code, self._code_verifier
            )
        except Exception:  # noqa: BLE001 — _auth.exchange_code can raise many things
            _LOGGER.exception("Authentication failed during code exchange")
            return None, "auth_failed"

        return tokens, None

    # --- Initial setup ---------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Single step: user pastes the redirect URL after logging in."""
        errors: dict[str, str] = {}

        if user_input is not None:
            redirect_url = user_input.get("redirect_url", "").strip()
            tokens, err = await self._exchange_redirect_url(redirect_url)
            if err:
                errors["base"] = err
            else:
                assert tokens is not None
                await self.async_set_unique_id(tokens.user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Sub-Zero Group",
                    data={CONF_TOKENS: tokens.to_dict()},
                    options={CONF_DEVICE_PINS: {}},
                )

        return self._show_login_form("user", errors=errors)

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> FlowResult:
        """Handle DHCP discovery of a Sub-Zero Group appliance on the network.

        DHCP finds individual appliances by MAC (OUI 00:06:80), but the
        integration is configured per-account (one config entry covers all
        appliances). If any config entry already exists, abort silently.
        Otherwise, prompt the user to set up their account.
        """
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {
            "name": discovery_info.hostname or "Sub-Zero Appliance",
        }
        return await self.async_step_user()

    # --- Reauth ----------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Trigger reauthentication when the cloud token can't be refreshed."""
        # Look up the entry HA selected via the context. Stored on the
        # flow instance so async_step_reauth_confirm can find it.
        entry_id = self.context.get("entry_id")
        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the same login form as initial setup and validate the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            redirect_url = user_input.get("redirect_url", "").strip()
            tokens, err = await self._exchange_redirect_url(redirect_url)
            if err:
                errors["base"] = err
            else:
                assert tokens is not None
                # Guard against logging in with a different Sub-Zero account.
                # The entry's unique_id is the original user_id; mismatch
                # here means the user authenticated as someone else.
                if (
                    self._reauth_entry is not None
                    and self._reauth_entry.unique_id is not None
                    and tokens.user_id != self._reauth_entry.unique_id
                ):
                    return self.async_abort(reason="reauth_account_mismatch")

                if self._reauth_entry is not None:
                    new_data = dict(self._reauth_entry.data)
                    new_data[CONF_TOKENS] = tokens.to_dict()
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data=new_data,
                    )

                # Should be unreachable, but if HA didn't give us an entry
                # (e.g. it was deleted between trigger and confirm), bail
                # out cleanly.
                return self.async_abort(reason="not_loaded")

        return self._show_login_form("reauth_confirm", errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SZGOptionsFlow:
        """Get the options flow for this handler."""
        return SZGOptionsFlow(config_entry)


class SZGOptionsFlow(OptionsFlow):
    """Handle options flow for entering device PINs."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._device_id: str | None = None

    def _existing_pins(self) -> dict[str, str]:
        """Return the device_pins dict regardless of whether the entry has
        been migrated yet (v1 stored it in data, v2 stores it in options).
        """
        return (
            self._config_entry.options.get(CONF_DEVICE_PINS)
            or self._config_entry.data.get(CONF_DEVICE_PINS)
            or {}
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Select a device and trigger PIN display."""
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if not coordinator:
            return self.async_abort(reason="not_loaded")

        existing_pins = self._existing_pins()
        eligible = {}
        for device_id, conn in coordinator.devices.items():
            if conn.supports_local:
                label = conn.name
                if device_id in existing_pins:
                    label += " (PIN already set)"
                eligible[device_id] = label

        if not eligible:
            return self.async_abort(reason="no_local_devices")

        if user_input is not None:
            self._device_id = user_input.get("device_id", "")

            # Trigger PIN display on the selected device
            if self._device_id and self._device_id in coordinator.devices:
                conn = coordinator.devices[self._device_id]
                try:
                    await conn.async_display_pin(self.hass)
                except Exception:
                    pass  # PIN display may fail if door is closed

            return await self.async_step_enter_pin()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(eligible),
            }),
        )

    async def async_step_enter_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Enter the PIN shown on the appliance display."""
        errors = {}

        if user_input is not None:
            pin = user_input.get("pin", "").strip()

            if len(pin) != 6 or not pin.isdigit():
                errors["base"] = "invalid_pin"
            else:
                # Validate the PIN against the appliance before saving
                coordinator = self.hass.data.get(DOMAIN, {}).get(
                    self._config_entry.entry_id
                )
                if coordinator and self._device_id in coordinator.devices:
                    conn = coordinator.devices[self._device_id]
                    ip = conn.appliance.ip_address
                    if not ip:
                        errors["base"] = "cannot_connect"
                    else:
                        try:
                            client = SZGClient(ip, pin=pin)
                            await self.hass.async_add_executor_job(client.refresh)
                        except PySZGAuthError:
                            errors["base"] = "wrong_pin"
                        except Exception:
                            errors["base"] = "cannot_connect"

                if not errors:
                    pins = dict(self._existing_pins())
                    pins[self._device_id] = pin
                    new_options = dict(self._config_entry.options)
                    new_options[CONF_DEVICE_PINS] = pins

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, options=new_options
                    )
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="enter_pin",
            data_schema=vol.Schema({
                vol.Required("pin"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEL)
                ),
            }),
            errors=errors,
        )
