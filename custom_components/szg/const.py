"""Constants for the Sub-Zero Group integration."""

from pyszg import ApplianceType

DOMAIN = "szg"
MANUFACTURER = "Sub-Zero Group"

CONF_TOKENS = "tokens"
CONF_DEVICE_PINS = "device_pins"

# Appliance categories that report the refrigerator property set
# (ref_/frz_ set temps, door ajar flags, ice maker, modes). Drawer
# combinations such as the ID30CI report category 2 (FREEZER).
REFRIGERATION_TYPES = (ApplianceType.REFRIGERATOR, ApplianceType.FREEZER)
