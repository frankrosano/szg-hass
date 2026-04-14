# Sub-Zero Group for Home Assistant

Home Assistant integration for Sub-Zero, Wolf, and Cove connected appliances.

Supports local IP control for older CAT-module appliances and cloud API for all appliances including newer models.

## Features

- Auto-discovers all appliances on your Sub-Zero account
- Cloud control and real-time push updates via SignalR for all appliances
- Optional local control for CAT-module appliances (faster, no cloud dependency)
- Tested with refrigerators, ovens, and dishwashers
- Other Sub-Zero Group appliance types (freezers, wine storage) should work but are untested

### Refrigerator
- Climate entities for fridge and freezer temperature control
- Door open/close binary sensors
- Ice maker mode selector (Off, Normal, Max Ice, Night Ice)
- Operating mode selector (Normal, High Use, Short Vacation, Long Vacation, Sabbath)
- Filter life sensors (air filter %, water filter %, water filter gallons remaining)
- Max ice and high use start/end time sensors
- Service required alert
- Accent light level control (disabled by default, for glass-front models)

### Oven
- Climate entities for upper and lower cavities (current temp, set temp, on/off)
- Cook mode selector for each cavity (Off, Bake, Roast, Broil, Convection, etc.)
- Light switches for each cavity
- Door and probe binary sensors for each cavity
- Remote ready binary sensors
- Remote start buttons (available only when Remote Ready is enabled on the oven)
- Cook timer and kitchen timer end time sensors
- Kitchen timer active binary sensors
- Kitchen timer duration controls (set in minutes, 0 to cancel)

### Dishwasher
- Wash cycle and wash status sensors
- Cycle end time sensor (for countdown automations)
- Door binary sensor
- Remote ready binary sensor
- Start wash cycle button (available only when Remote Ready is enabled)
- Delay start selector (Off, 1–12 hours)
- Switches for heated dry, extended dry, high temp wash, sani rinse, top rack only
- Rinse aid low and softener low alerts

### All Appliances
- Connection mode diagnostic sensor (Local or Cloud)
- Live reporting mode diagnostic sensor (Local Push, Cloud Push, or Cloud Polling)
- IP address, MAC address, and uptime diagnostic sensors (disabled by default)
- Download diagnostics support for troubleshooting

## Installation (HACS)

1. Add this repository as a custom repository in HACS
2. Install "Sub-Zero Group"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add Integration → "Sub-Zero Group"
5. Log in with your Sub-Zero Owner's App account

## Local Control Setup

For CAT-module appliances (those supporting Control4/Crestron/Savant), local control provides faster response and no cloud dependency:

1. After adding the integration, go to Settings → Integrations → Sub-Zero Group → Configure
2. Select the appliance you want to enable local control for
3. Open a door on the appliance, then click Submit
4. The 6-digit PIN will appear on the appliance's display
5. Enter the PIN and click Submit

Local control is now active — commands and state updates will use the local network instead of the cloud. The integration automatically detects the appliance's IP address from the cloud API.

## Requirements

- Sub-Zero Owner's App account with appliances registered
- Network connectivity to appliances (for local control)
- Internet connectivity (for cloud API and initial setup)
