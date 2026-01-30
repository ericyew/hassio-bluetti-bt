"""Bluetti Bluetooth Config Flow"""

from __future__ import annotations
import re
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth  # Added this import
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult
from bluetti_bt_lib import recognize_device

from .types import InitialDeviceConfig, ManufacturerData, OptionalDeviceConfig
from .const import DOMAIN, CONF_DEVICE_TYPE

_LOGGER = logging.getLogger(__name__)

DEVICE_OPTIONS = [
    "Auto Detect",
    "AC2P",
    "AC2A",
    "EB3A",
    "AC200M",
    "AC300",
    "AC500",
    "EP500",
    "EP600",
    "EB70",
]

class BluettiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Bluetti BT devices."""

    def __init__(self) -> None:
        _LOGGER.info("Initialize config flow")
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Get device type
        recognized = await recognize_device(
            discovery_info.address, self.hass.loop.create_future
        )

        if recognized is None:
            return self.async_abort(reason="Device type not supported")

        _LOGGER.info(
            "Device identified as %s with iot module version %s (using encryption: %s)",
            recognized.name,
            recognized.iot_version,
            recognized.encrypted,
        )

        discovery_info.manufacturer_data = ManufacturerData(
            recognized.name, recognized.encrypted
        ).as_dict
        discovery_info.name = recognized.full_name
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user input."""
        
        # 1. HANDLE FORM SUBMISSION
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            manual_type = user_input.get(CONF_DEVICE_TYPE, "Auto Detect")

            # Find the discovery info again for the selected address
            service_infos = bluetooth.async_discovered_service_info(self.hass)
            discovery_info = next(
                (service_info for service_info in service_infos if service_info.address == address),
                self._discovery_info  # Fallback to existing info if available
            )

            if not discovery_info:
                return self.async_abort(reason="device_not_found")

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            
            name = re.sub("[^A-Z0-9]+", "", discovery_info.name)

            manufacturer_data = ManufacturerData.from_dict(
                discovery_info.manufacturer_data
            )
            
            # <--- NEW: LOGIC TO OVERRIDE DEVICE TYPE
            dev_type = manufacturer_data.dev_type
            if manual_type != "Auto Detect":
                dev_type = manual_type

            data = InitialDeviceConfig(
                address,
                name,
                dev_type,  # Use the potentially overridden type
                manufacturer_data.use_encryption,
            )

            optional = OptionalDeviceConfig.from_dict({})

            return self.async_create_entry(
                title=name,
                data={
                    **data.as_dict,
                    **optional.as_dict,
                },
            )

        # 2. SCAN FOR DEVICES (If no input provided)
        service_infos = bluetooth.async_discovered_service_info(self.hass)
        choices = {}
        
        for discovery_info in service_infos:
            name = discovery_info.name
            # Filter for likely Bluetti devices
            if name.startswith(("AC", "EB", "EP", "BLUETTI")):
                choices[discovery_info.address] = f"{name} ({discovery_info.address})"

        if not choices:
            return self.async_abort(reason="no_devices_found")

        # 3. SHOW FORM WITH DROPDOWNS
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(choices),
                    vol.Optional(CONF_DEVICE_TYPE, default="Auto Detect"): vol.In(DEVICE_OPTIONS)
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(_) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # 1. Extract the selected device type
            manual_type = user_input.get(CONF_DEVICE_TYPE)

            # 2. Handle existing optional config (polling, logging, etc.)
            config = OptionalDeviceConfig.from_dict(user_input)
            reason = config.validate()

            if reason is not None:
                return self.async_abort(reason=reason)

            # 3. Update the entry
            # We follow the existing pattern of updating 'data', 
            # but we also return the new values to update 'options'.
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    **config.as_dict,
                },
            )
            
            # This saves the config to entry.options
            return self.async_create_entry(
                title="",
                data={
                    **config.as_dict,
                    CONF_DEVICE_TYPE: manual_type,  # Save the manual type to options
                },
            )

        # 4. Build the Schema
        # Load existing defaults from data
        defaults = OptionalDeviceConfig.from_dict(self.config_entry.data)
        
        # Determine current device type
        # Priority: Options (User Edit) -> Data (Initial Setup) -> Default
        current_type = self.config_entry.options.get(
            CONF_DEVICE_TYPE, 
            self.config_entry.data.get(CONF_DEVICE_TYPE, "Auto Detect")
        )

        # Extend the schema to include the Device Type dropdown
        schema = defaults.schema.extend({
            vol.Optional(CONF_DEVICE_TYPE, default=current_type): vol.In(DEVICE_OPTIONS)
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
