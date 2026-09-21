# DeskPal: website or desktop application?

For this project, the desktop application is the better foundation. Keep the website as a convenient dashboard for the app. If you choose only one, choose the desktop application.

This comparison refers to the website and Python application in this folder. It is based on source inspection, not a new runtime or performance test.

## What you have now

| Option | Current purpose | Main limitation |
| --- | --- | --- |
| Desktop app (`deskpal.py`) | Runs the floating character, animations, reminders, and Windows integration. | The source version requires Python and tkinter; installation and settings can be made easier. |
| Local website (`ganesh_showcase.html`) | Launches the desktop companion and sends animation commands. | Requires the local launcher service and desktop app for those actions. |
| Dashboard (`deskpal_dashboard.html`) | Shows controls, an exercise list, and reminder selectors. | Some information is browser-only and is not connected to the desktop reminder engine. |

The existing website runs through `deskpal_launch_server.py` at `http://127.0.0.1:8766/`. It is a local interface on your computer. Uploading these HTML files to a public host would not reproduce the desktop functionality: their API requests currently depend on the local Python service.

## Why the application is the better foundation

DeskPal's main value is the companion on the desktop while you use other programs. The Python code contains the Windows window behavior, battery and activity integration, and reminder logic. The current web pages call that application; they do not replace it.

The website is useful for organizing settings, showing progress, and providing clear controls. Combining that interface with the existing desktop engine preserves the work already done and avoids rebuilding the core features.

Recommended structure:

`Local dashboard -> local launcher/API -> desktop companion`

Keep reminder scheduling in the desktop application so closing the dashboard does not stop the reminders.

## Changes I suggest, in priority order

1. **Connect dashboard settings to the desktop app.** Currently, reminder selectors write to browser `localStorage`, but the server has no reminder-settings endpoint. Add validated read/update endpoints and desktop commands to apply changes. Load the actual saved settings when the dashboard opens and show success only after the app acknowledges the update.

2. **Show real reminder information.** The dashboard starts with a fixed "Water / in 60 minutes" label. Changing a selector changes that text; it does not read the actual next reminder. Have the desktop engine report its next reminder and remaining time, including paused or quiet states.

3. **Make exercise storage reliable.** The dashboard parses stored JSON without error handling and inserts exercise names through `innerHTML`. Handle missing or invalid saved data, validate the stored structure and duration, and render names using `textContent`. Decide whether completed exercises reset daily; the current count does not implement a daily reset despite its "Today's movement" label.

4. **Improve connection and launch feedback.** Distinguish "launcher unavailable", "app stopped", "starting", and "running". Give the dashboard requests a timeout, prevent repeated launch clicks while starting, and display useful errors inline. Confirm visibility before saying the character is on the desktop. The showcase page already implements some of these protections and can guide the dashboard changes.

5. **Simplify startup and packaging.** Provide one obvious way to start DeskPal and open its dashboard. Handle an occupied launcher port with a readable message. A `DeskPal-Windows` distribution already exists, but verify that its executable and assets match the current source before treating it as the release. Keep direct desktop launch available.

6. **Improve presentation after the connections work.** Group the dashboard into Today, Reminders, Character, and Settings. Use consistent names and controls, readable text, keyboard access, and layouts that fit smaller windows. Keep animation assets shared between the relevant components where practical.

## How to reduce errors before release

- Check launch, repeated launch, closing and reopening the dashboard, and restarting the app.
- Confirm a dashboard reminder change reaches the desktop engine and survives restart.
- Check invalid saved browser data, missing animation assets, unavailable services, and occupied ports.
- Check character visibility, animation commands, monitor changes, and display scaling.
- Run the existing `verify_launch.py` in its configured environment. It covers launch and emotes, but additional checks are needed for settings synchronization and dashboard recovery.

No review can promise zero future errors. These are proposed improvements; this task only adds this explanation and does not change application code or certify a release.

**Recommendation:** improve the existing desktop app and connect the local dashboard properly. A website-only replacement would not preserve the current desktop companion behavior as implemented.
