# AmbiWiz

AmbiWiz is a lightweight ambient lighting application for Linux desktops running GNOME on Wayland.

It captures the desktop using the GNOME ScreenCast portal, receives the captured frames through PipeWire and GStreamer, analyzes the colors displayed on the screen, and sends RGB commands directly to WiZ smart lights over the local network.

The goal is simple: make the lights around your display react to what is currently being shown on the screen without relying on a cloud service or a separate lighting application.

## Features

* Designed for GNOME on Wayland
* Uses the GNOME ScreenCast portal for desktop capture
* Uses PipeWire for screen frame delivery
* Uses GStreamer for video processing
* Supports multiple captured displays
* Automatically determines the left and right sides of the desktop
* Samples the screen instead of processing every pixel
* Ignores nearly-black pixels
* Smooths color transitions
* Avoids sending unnecessary WiZ commands
* Communicates directly with WiZ lights over the local network
* No cloud service required
* Runs continuously until stopped

## How It Works

AmbiWiz follows this basic pipeline:

```text
GNOME Desktop
     |
     v
GNOME ScreenCast Portal
     |
     v
   PipeWire
     |
     v
  GStreamer
     |
     v
RGBA Screen Frames
     |
     v
Color Sampling
     |
     +----------------+
     |                |
     v                v
 Left Side       Right Side
     |                |
     v                v
 Color Average    Color Average
     |                |
     +-------+--------+
             |
             v
       Color Smoothing
             |
             v
         WiZ UDP API
             |
             v
        WiZ Smart Lights
```

The desktop is divided into left and right regions based on the horizontal bounds of the captured screens.

Each captured stream is analyzed and assigned to either the left or right side of the desktop. The colors from streams belonging to the same side are averaged together.

The resulting colors are then smoothed before being sent to the lights.

---

# Requirements

AmbiWiz is intended for Linux systems using:

* GNOME
* Wayland
* PipeWire
* WirePlumber
* GNOME ScreenCast
* GStreamer
* Python 3

Ubuntu and Debian-based systems are currently the primary target.

The application is not designed for X11 screen capture.

---

# Installation

The project includes an installation script that installs the required system dependencies and verifies that the important components are available.

Clone or copy the project to your computer, then enter the project directory:

```bash
cd AmbiWiz
```

Make the installer executable:

```bash
chmod +x install-dependencies.sh
```

Run the installer:

```bash
sudo ./install-dependencies.sh
```

The installer will:

1. Update the system package lists.
2. Install Python 3.
3. Install Python D-Bus bindings.
4. Install Python GObject/GStreamer bindings.
5. Install GStreamer.
6. Install the GStreamer PipeWire plugin.
7. Install GStreamer Base and Good plugins.
8. Install PipeWire.
9. Install WirePlumber.
10. Install the XDG desktop portal.
11. Install the GNOME desktop portal backend.
12. Verify the required Python modules.
13. Verify the required GStreamer elements.

The installer checks for:

```text
pipewiresrc
videoconvert
capsfilter
appsink
```

before reporting a successful installation.

---

# Dependencies

The installation script installs the following packages:

```text
python3
python3-dbus
python3-gi
gir1.2-gstreamer-1.0
gstreamer1.0-pipewire
gstreamer1.0-plugins-base
gstreamer1.0-plugins-good
pipewire
wireplumber
xdg-desktop-portal
xdg-desktop-portal-gnome
```

No Python packages need to be installed with `pip`.

The project uses the Python modules provided by the operating system packages.

---

# Checking the Installation

After running the installer, check that the desktop session is using Wayland:

```bash
echo "$XDG_SESSION_TYPE"
```

The expected result is:

```text
wayland
```

You can also verify the GStreamer PipeWire source:

```bash
gst-inspect-1.0 pipewiresrc
```

The command should display information about the `pipewiresrc` element.

The other required GStreamer elements can be checked with:

```bash
gst-inspect-1.0 videoconvert
gst-inspect-1.0 capsfilter
gst-inspect-1.0 appsink
```

PipeWire can be checked with:

```bash
systemctl --user status pipewire
```

WirePlumber can be checked with:

```bash
systemctl --user status wireplumber
```

The GNOME desktop portal can be checked with:

```bash
systemctl --user status xdg-desktop-portal
```

---

# Configuration

The main configuration is located near the beginning of `ambiwiz.py`.

```python
LEFT_LIGHT = "10.0.0.153"
RIGHT_LIGHT = "10.0.0.50"

WIZ_PORT = 38899

UPDATE_INTERVAL = 0.10

SMOOTHING = 0.20

COLOR_THRESHOLD = 5

DARK_THRESHOLD = 25

CURSOR_MODE = 2

SAMPLE_COLUMNS = 32
SAMPLE_ROWS = 18
```

## WiZ Light Addresses

Set `LEFT_LIGHT` to the IP address of the WiZ light on the left:

```python
LEFT_LIGHT = "10.0.0.153"
```

Set `RIGHT_LIGHT` to the IP address of the WiZ light on the right:

```python
RIGHT_LIGHT = "10.0.0.50"
```

The computer and the lights must be able to communicate with each other over the local network.

If your router assigns IP addresses using DHCP, it is recommended to create DHCP reservations for the lights so their addresses do not change.

---

# WiZ UDP Port

WiZ local control uses UDP port `38899`.

The default configuration is:

```python
WIZ_PORT = 38899
```

There normally should be no reason to change this.

---

# Color Updates

## Update Interval

```python
UPDATE_INTERVAL = 0.10
```

This controls how frequently AmbiWiz recalculates the screen colors.

The default value of `0.10` results in approximately 10 update cycles per second.

For more frequent updates:

```python
UPDATE_INTERVAL = 0.05
```

For less frequent updates:

```python
UPDATE_INTERVAL = 0.20
```

Lower values can increase CPU usage and network traffic.

---

# Color Smoothing

```python
SMOOTHING = 0.20
```

Smoothing controls how quickly the current color moves toward the newly calculated screen color.

A higher value produces faster reactions:

```python
SMOOTHING = 0.40
```

A lower value produces slower, smoother transitions:

```python
SMOOTHING = 0.10
```

The default value of `0.20` is intended to provide a balance between responsiveness and smooth transitions.

---

# Color Threshold

```python
COLOR_THRESHOLD = 5
```

AmbiWiz does not send a new WiZ command for every tiny color change.

A new command is sent only when at least one RGB channel has changed by the configured threshold.

For example:

```text
Previous: (120, 80, 50)
Current:  (122, 82, 51)
```

would normally be ignored with a threshold of `5`.

This reduces unnecessary network traffic and prevents constant small adjustments.

A lower value makes the lights more responsive:

```python
COLOR_THRESHOLD = 2
```

A higher value makes them more stable:

```python
COLOR_THRESHOLD = 10
```

---

# Dark Pixel Filtering

```python
DARK_THRESHOLD = 25
```

Very dark pixels are ignored when calculating the average screen color.

AmbiWiz calculates:

```text
R + G + B
```

and ignores the pixel when the result is below the configured threshold.

This is particularly useful when watching movies or videos with black borders.

If too much of the screen is being ignored, the threshold can be lowered:

```python
DARK_THRESHOLD = 10
```

---

# Cursor Capture

```python
CURSOR_MODE = 2
```

This value is passed to the GNOME ScreenCast portal.

The current configuration tells the portal not to include the mouse cursor in the captured image.

---

# Screen Sampling

AmbiWiz does not inspect every pixel in every frame.

Instead, it samples the screen using:

```python
SAMPLE_COLUMNS = 32
SAMPLE_ROWS = 18
```

This produces an effective sampling grid of approximately:

```text
32 × 18
```

This is enough to get a representative screen color without unnecessarily increasing CPU usage.

For more detailed sampling:

```python
SAMPLE_COLUMNS = 64
SAMPLE_ROWS = 36
```

For lower CPU usage:

```python
SAMPLE_COLUMNS = 16
SAMPLE_ROWS = 9
```

---

# Running AmbiWiz

Make the Python script executable:

```bash
chmod +x ambiwiz.py
```

Then run:

```bash
./ambiwiz.py
```

You can also run it directly through Python:

```bash
python3 ambiwiz.py
```

A successful startup should look similar to:

```text
==========================================
 WiZ Wayland Ambilight
==========================================

LEFT  → 10.0.0.153
RIGHT → 10.0.0.50

Capture: GNOME ScreenCast / PipeWire

Portal session created.
Screen source selected.
Portal returned 1 screen stream(s).

PipeWire connection opened (fd=...)

Screen stream: node=... position=(...) size=(...)

Ambilight is running.
Left light : 10.0.0.153
Right light: 10.0.0.50

Press Ctrl+C to stop.
```

Press `Ctrl+C` to stop AmbiWiz.

---

# Multiple Displays

AmbiWiz supports multiple ScreenCast streams.

When several displays are captured, GNOME provides information about each stream's position and size.

For example:

```text
Screen stream: node=42 position=(0, 0) size=(1920, 1080)
Screen stream: node=43 position=(1920, 0) size=(1920, 1080)
```

AmbiWiz uses these positions to determine the overall desktop boundaries.

The center of the combined desktop is then used to determine whether a screen belongs to the left or right side.

Colors from multiple streams on the same side are averaged together.

This means the application does not need to know the monitor resolution or arrangement in advance.

---

# Current Light Behavior

The current version of AmbiWiz intentionally sends the calculated **right-side color to both lights**.

The current behavior is therefore:

```text
LEFT LIGHT  ← RIGHT RGB
RIGHT LIGHT ← RIGHT RGB
```

The left-side color is still calculated and smoothed internally, but the current update logic uses `right_rgb` for both lights.

This is intentional and preserves the current behavior of the script.

## Independent Left and Right Colors

If you want each light to follow its corresponding side of the screen, the update section can be changed to:

```python
if color_changed(last_left_sent, left_rgb):
    send_wiz_color(
        LEFT_LIGHT,
        left_rgb,
    )

    last_left_sent = list(left_rgb)

if color_changed(last_right_sent, right_rgb):
    send_wiz_color(
        RIGHT_LIGHT,
        right_rgb,
    )

    last_right_sent = list(right_rgb)
```

The resulting behavior would then be:

```text
LEFT LIGHT  ← LEFT RGB
RIGHT LIGHT ← RIGHT RGB
```

---

# GStreamer Pipeline

Each captured screen stream is processed using a GStreamer pipeline:

```text
pipewiresrc
     |
     v
videoconvert
     |
     v
capsfilter
     |
     v
appsink
```

The captured frames are converted to:

```text
video/x-raw,format=RGBA
```

The `appsink` is configured to keep only the most recent frame:

```python
max-buffers = 1
drop = True
```

This prevents old frames from accumulating if color processing falls behind.

AmbiWiz therefore prioritizes processing the current screen rather than attempting to process every frame.

---

# Thread Safety

Captured frames are shared between the GStreamer callback and the color analysis code.

Each stream has its own lock.

The latest frame is copied while the lock is held, after which the lock is released before the more expensive color analysis takes place.

This keeps frame capture responsive and prevents the color analysis from unnecessarily blocking GStreamer.

---

# WiZ Communication

AmbiWiz communicates directly with WiZ lights using UDP.

A typical command looks like:

```json
{
    "method": "setPilot",
    "params": {
        "state": true,
        "r": 255,
        "g": 0,
        "b": 0
    }
}
```

The command is sent to:

```text
LIGHT_IP:38899
```

For example:

```text
10.0.0.153:38899
```

No WiZ cloud account or external server is required for the color commands.

---

# Network Requirements

The computer running AmbiWiz and the WiZ lights must be able to communicate over the local network.

For example:

```bash
ping 10.0.0.153
```

and:

```bash
ping 10.0.0.50
```

should normally succeed if ICMP is enabled on the network.

If the lights are unreachable, verify:

* The IP addresses are correct.
* The computer and lights are on the same network.
* The lights are powered on.
* UDP traffic is not being blocked.
* The router is not isolating wireless clients from wired clients.
* The WiZ lights have not received new DHCP addresses.

---

# Troubleshooting

## `ERROR starting screen capture`

First check the session type:

```bash
echo "$XDG_SESSION_TYPE"
```

It should return:

```text
wayland
```

Then check PipeWire:

```bash
systemctl --user status pipewire
```

and WirePlumber:

```bash
systemctl --user status wireplumber
```

Also check the desktop portal:

```bash
systemctl --user status xdg-desktop-portal
```

and:

```bash
systemctl --user status xdg-desktop-portal-gnome
```

---

## `Could not create GStreamer elements`

Run:

```bash
gst-inspect-1.0 pipewiresrc
```

If `pipewiresrc` cannot be found, run the dependency installer again:

```bash
sudo ./install-dependencies.sh
```

Also verify:

```bash
gst-inspect-1.0 videoconvert
gst-inspect-1.0 capsfilter
gst-inspect-1.0 appsink
```

---

## Python cannot import `dbus`

Run:

```bash
python3 -c "import dbus; print('D-Bus OK')"
```

If this fails, reinstall the package:

```bash
sudo apt install python3-dbus
```

---

## Python cannot import GStreamer

Run:

```bash
python3 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('GStreamer OK')"
```

If this fails:

```bash
sudo apt install python3-gi gir1.2-gstreamer-1.0
```

---

## The lights do not respond

Verify the configured addresses:

```python
LEFT_LIGHT = "10.0.0.153"
RIGHT_LIGHT = "10.0.0.50"
```

Check basic network connectivity:

```bash
ping 10.0.0.153
ping 10.0.0.50
```

If the addresses are correct but the lights still do not react, check whether UDP port `38899` is being blocked by the local firewall or network configuration.

---

## Colors are too slow

Increase:

```python
SMOOTHING = 0.20
```

For example:

```python
SMOOTHING = 0.40
```

You can also reduce:

```python
UPDATE_INTERVAL = 0.10
```

to:

```python
UPDATE_INTERVAL = 0.05
```

---

## Colors change too aggressively

Reduce the smoothing value:

```python
SMOOTHING = 0.10
```

or increase the threshold:

```python
COLOR_THRESHOLD = 10
```

---

## The lights remain too dark

Try lowering:

```python
DARK_THRESHOLD = 25
```

For example:

```python
DARK_THRESHOLD = 10
```

This allows darker pixels to contribute to the calculated color.

---

## CPU usage is too high

Reduce the sampling resolution:

```python
SAMPLE_COLUMNS = 16
SAMPLE_ROWS = 9
```

You can also increase the update interval:

```python
UPDATE_INTERVAL = 0.20
```

---

# Running Automatically

AmbiWiz can be run as a user-level systemd service.

This is preferable to running it as a system service because GNOME ScreenCast, D-Bus, PipeWire, and the Wayland session belong to the logged-in desktop user.

Create the service directory:

```bash
mkdir -p ~/.config/systemd/user
```

Create:

```text
~/.config/systemd/user/ambiwiz.service
```

with:

```ini
[Unit]
Description=AmbiWiz Wayland Ambient Lighting
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/ambiwiz.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Replace:

```text
/path/to/ambiwiz.py
```

with the actual path to the script.

Then reload systemd:

```bash
systemctl --user daemon-reload
```

Enable the service:

```bash
systemctl --user enable ambiwiz.service
```

Start it:

```bash
systemctl --user start ambiwiz.service
```

Check the service:

```bash
systemctl --user status ambiwiz.service
```

View live logs:

```bash
journalctl --user -u ambiwiz.service -f
```

---

# Stopping the Service

To stop AmbiWiz:

```bash
systemctl --user stop ambiwiz.service
```

To prevent it from starting automatically:

```bash
systemctl --user disable ambiwiz.service
```

---

# Privacy

AmbiWiz processes the captured screen locally.

Screen frames are held in memory only long enough to calculate the ambient colors.

The application does not upload screenshots or screen contents to an external service.

Only the resulting RGB commands are sent across the local network to the WiZ lights.

---

# Limitations

The current version has several limitations:

* Requires GNOME on Wayland.
* Requires PipeWire.
* Requires GStreamer with `pipewiresrc`.
* Requires the GNOME ScreenCast portal.
* Requires WiZ lights that support local UDP control.
* WiZ lights must be reachable over the local network.
* WiZ light discovery is not currently automatic.
* WiZ addresses are configured directly in the Python script.
* The current version intentionally sends the right-side color to both lights.
* Configuration is currently stored directly in the Python source.
* The application does not currently provide a graphical configuration interface.
* A lost ScreenCast session requires the capture pipeline to be restarted.

---

# Project Structure

A basic AmbiWiz installation looks like:

```text
AmbiWiz/
├── ambiwiz.py
├── install-dependencies.sh
└── README.md
```

## `ambiwiz.py`

The main AmbiWiz application.

It handles:

* GNOME ScreenCast
* D-Bus communication
* PipeWire
* GStreamer
* Screen color analysis
* Color smoothing
* WiZ UDP communication

## `install-dependencies.sh`

Installs and verifies the required system dependencies.

Run it with:

```bash
sudo ./install-dependencies.sh
```

## `README.md`

Project documentation and configuration reference.

---

# Quick Start

For a fresh Ubuntu/Debian GNOME Wayland installation:

```bash
cd AmbiWiz
```

Make the installer executable:

```bash
chmod +x install-dependencies.sh
```

Install the dependencies:

```bash
sudo ./install-dependencies.sh
```

Make AmbiWiz executable:

```bash
chmod +x ambiwiz.py
```

Edit the WiZ addresses:

```bash
nano ambiwiz.py
```

Set:

```python
LEFT_LIGHT = "YOUR_LEFT_LIGHT_IP"
RIGHT_LIGHT = "YOUR_RIGHT_LIGHT_IP"
```

Then start AmbiWiz:

```bash
./ambiwiz.py
```

If everything is configured correctly, the GNOME ScreenCast portal will start the capture session and the lights will begin responding to the calculated screen colors.

Press `Ctrl+C` to stop.

---

# License

No license is currently specified for AmbiWiz.

If you intend to publish or distribute the project, add a license such as MIT, GPL-3.0, or another license appropriate for the project.

---

# About

AmbiWiz is intended to be a simple, local, and lightweight way of adding ambient lighting to a Linux Wayland desktop using WiZ smart lights.

It relies on standard Linux desktop components rather than a proprietary screen-capture system, allowing the application to work directly with GNOME, PipeWire, GStreamer, and the local WiZ protocol.
