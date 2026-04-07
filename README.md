# Sub-Zero Group for Home Assistant

Home Assistant integration for Sub-Zero, Wolf, and Cove connected appliances.

Supports local IP control for older CAT-module appliances and cloud API for all appliances including newer models.

## Features

- Auto-discovers all appliances on your Sub-Zero account
- Automatically selects local or cloud control per appliance
- Real-time push updates via SignalR (cloud) and local TLS push (CAT modules)
- Supports refrigerators, ovens, and dishwashers

### Refrigerator
- Climate entities for fridge and freezer temperature control
- Door open/close binary sensors
- Switches for ice maker, max ice, night ice, vacation modes, sabbath
- Filter life sensors (air and water)

### Oven
- Temperature sensors for each cavity (actual and set point)
- Cook mode sensor (Bake, Roast, Convection, etc.)
- Door and probe binary sensors
- Light switches for each cavity
- Remote start/stop (requires physical "Remote Ready" on the oven)

### Dishwasher
- Wash cycle and status sensors
- Cycle end time sensor (for countdown automations)
- Door binary sensor
- Rinse aid and softener low alerts
- Heated dry and top rack only switches

## Installation (HACS)

1. Add this repository as a custom repository in HACS
2. Install "Sub-Zero Group"
3. Restart Home Assistant
4. Go to Settings → Integrations → Add Integration → "Sub-Zero Group"
5. Log in with your Sub-Zero Owner's App account

## Local Control Setup

For CAT-module appliances (those supporting Control4/Crestron/Savant), local control provides faster response and no cloud dependency:

1. After adding the integration, each CAT appliance will have a "Show PIN" button
2. Open a door on the appliance
3. Press the "Show PIN" button in Home Assistant
4. Read the 6-digit PIN from the appliance's display
5. Go to the integration's options and enter the PIN for that device

## Requirements

- Sub-Zero Owner's App account with appliances registered
- Network connectivity to appliances (for local control)
- Internet connectivity (for cloud API and initial setup)
