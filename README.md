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
5. Enter the email and password of your Sub-Zero Owner's App account. The password is used once to sign in and is never stored; only the resulting session tokens are kept.
6. If the password sign-in cannot complete on its own (for example if Sub-Zero changes its sign-in page or adds multi-factor authentication, which it does not currently offer), Home Assistant switches to a browser-based fallback automatically. You can also tick **Log in with browser instead** to use it directly (see below).

### Browser login (fallback)

Sub-Zero's browser login redirects to a URL that browsers cannot open, so you copy it from the developer console:

1. Before clicking the login link in the form, open developer tools (F12 or Cmd+Option+I) and switch to the **Console** tab.
2. Open the login link and sign in. The redirect page will fail to load, which is expected.
3. In the Console, find the navigation error containing a URL starting with `msauth.com.subzero.group.owners.app://auth?code=...`.
4. Copy the full URL and paste it into the form.

## Local Control Setup

For CAT-module appliances (those supporting Control4/Crestron/Savant), local control provides faster response and no cloud dependency:

1. After adding the integration, go to Settings → Integrations → Sub-Zero Group → Configure
2. Select the appliance you want to enable local control for
3. Open a door on the appliance, then click Submit
4. The 6-digit PIN will appear on the appliance's display
5. Enter the PIN and click Submit

Local control is now active — commands and state updates will use the local network instead of the cloud. The integration automatically detects the appliance's IP address from the cloud API.

## Re-authentication

If your Sub-Zero password changes or your account session is invalidated, Home Assistant will surface a reauthentication banner on the integration card. Click **Reconfigure** and sign in again with your email and password (the email is prefilled). If that does not work, use the browser login fallback described above. Entity history, customizations, and PIN settings are preserved — there is no need to remove and re-add the integration.

You must log in with the same Sub-Zero account that the integration was originally set up with. If you log in with a different account the flow will abort and ask you to retry.

## Troubleshooting

- **"Sub-Zero requires an extra sign-in step"**: the password sign-in could not complete on its own (for example a consent page, a changed sign-in page, or MFA if Sub-Zero ever adds it). Use the browser login that the form then shows.
- **"Could not reach the Sub-Zero service"**: Sub-Zero's login service sometimes returns transient errors. Wait a moment and try again.
- **"Invalid email or password"**: check your credentials in the Owner's App. Avoid repeated failed attempts in case the account is temporarily locked.

## Requirements

- Sub-Zero Owner's App account with appliances registered
- Network connectivity to appliances (for local control)
- Internet connectivity (for cloud API and initial setup)
