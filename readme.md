# AmbiWiz

AmbiWiz turns WiZ smart lights into ambient lighting for a Linux desktop. It watches what is on your screen and sets every light in one WiZ room to the screen's main color, many times per second.

Everything runs locally. Screen frames never leave your computer, and the lights are controlled directly over your home network with no cloud account.

It works with normal windows and with fullscreen apps such as games and videos.

## Requirements

* Linux with **GNOME on Wayland** (X11 is not supported)
* PipeWire and the GNOME desktop portal (standard on recent Ubuntu and Fedora)
* Python 3 and GStreamer (installed by the script below)
* WiZ color lights on the same local network as the computer

Ubuntu and other Debian-based systems are the main target. The installer uses `apt`.

## Quick start

```bash
cd AmbiWiz

# 1. Install the system packages
chmod +x install-dependencies.sh
sudo ./install-dependencies.sh

# 2. Set your network in wiz_scanner.py (see below), then find your lights
python3 wiz_scanner.py

# 3. Put your room ID into ambiwiz.py (see below), then start
python3 ambiwiz.py
```

When AmbiWiz starts, GNOME asks which screen to share. Pick your screen, or all screens, and click **Share**. The lights start following the screen right away.

Press `Ctrl+C` to stop.

---

## Step 1: Install dependencies

```bash
chmod +x install-dependencies.sh
sudo ./install-dependencies.sh
```

The installer installs these packages with `apt`:

```text
python3                      python3-dbus
python3-gi                   gir1.2-gstreamer-1.0
gir1.2-gst-plugins-base-1.0  gstreamer1.0-pipewire
gstreamer1.0-plugins-base    gstreamer1.0-plugins-good
gstreamer1.0-gl              pipewire
wireplumber                  xdg-desktop-portal
xdg-desktop-portal-gnome
```

It then checks that Python can load D-Bus and GStreamer, and that the GStreamer elements AmbiWiz uses are present. No `pip` packages are needed.

If the GPU elements (`glupload` and friends) are missing, the installer prints a warning instead of failing. AmbiWiz still runs, but fullscreen windows may freeze the lights (see [Fullscreen windows](#fullscreen-windows)).

## Step 2: Find your lights

`wiz_scanner.py` checks every address on your network for WiZ lights. It saves what it finds, grouped by WiZ room, in `wiz_lights.json` next to the script.

First, open `wiz_scanner.py` and set `NETWORK` to your home network:

```python
NETWORK = "192.168.0.0/24"
```

If you don't know it, run `ip -4 addr` and look at your Wi-Fi or Ethernet address. For example, `inet 10.0.0.42/24` means `NETWORK = "10.0.0.0/24"`.

Then run the scanner:

```bash
python3 wiz_scanner.py
```

Checking a whole `/24` network can take about two minutes. The result looks like this:

```text
Found 3 WiZ device(s).

Rooms:

Room 12304474: 2 light(s)
    10.0.0.50  ESP24_SHRGB_01  MAC=cc40...
    10.0.0.153  ESP24_SHRGB_01  MAC=cc40...

Room 12304538: 1 light(s)
    10.0.0.95  ESP24_SHRGB_01  MAC=cc40...
```

The lights don't report their room names, only room numbers. To tell rooms apart, compare the IP addresses with the WiZ app or your router's device list.

Run the scanner again whenever you add a light, move one to another room, or a light's IP address changes. Reserving fixed addresses for the lights in your router avoids that last case.

## Step 3: Choose the room

Open `ambiwiz.py` and set `WIZ_ROOM_ID` to a room number from the scan:

```python
WIZ_ROOM_ID = 12304474  # Office
```

Every light in that room becomes part of one lighting zone, and they all show the same color.

## Step 4: Run AmbiWiz

```bash
python3 ambiwiz.py
```

GNOME shows a screen-sharing dialog. Choose the screen(s) to follow and click **Share**. While AmbiWiz runs, GNOME shows its screen-sharing indicator in the top bar.

A successful start ends like this:

```text
Portal returned 1 screen stream(s).
PipeWire connection opened (fd=...).
Screen stream: node=... position=(0, 0) size=(1920, 1080)
Stream ...: capturing with GPU pipeline.

AmbiWiz is running.
Mode: Single illumination zone
Lights: 2

Press Ctrl+C to stop.
```

If you share several monitors, all of them are blended into the one zone color.

---

## Keeping your own settings

The `.gitignore` excludes any file named `*_local.*`, along with `wiz_lights.json`. To keep your own settings out of git and avoid conflicts when you pull updates, run a personal copy:

```bash
cp ambiwiz.py ambiwiz_local.py
python3 ambiwiz_local.py
```

After pulling a new version, copy `ambiwiz.py` again and re-apply your settings.

---

## Settings

All settings are at the top of `ambiwiz.py`. The defaults are shown.

### Lights

| Setting | Default | Meaning |
| --- | --- | --- |
| `WIZ_ROOM_ID` | — | WiZ room to control (from `wiz_scanner.py`). |
| `WIZ_PORT` | `38899` | WiZ local control port. You normally never change this. |

### Response

| Setting | Default | Meaning |
| --- | --- | --- |
| `UPDATE_INTERVAL` | `0.05` | Seconds between updates. `0.05` is 20 per second. |
| `SMOOTHING` | `0.25` | How fast the lights follow the screen, from `0` to `1`. Higher is faster and `1` means no smoothing. Lower is calmer. |
| `COLOR_THRESHOLD` | `2` | Skip sending a color if no channel changed by at least this much (0–255). Higher means fewer, steadier updates. |

### Color

| Setting | Default | Meaning |
| --- | --- | --- |
| `SATURATION_BOOST` | `1.60` | Makes colors more vivid. `1.0` is unchanged, `1.3` is noticeable and `2.0` is very strong. |
| `BRIGHTNESS_BOOST` | `1.35` | Makes the lights brighter. `1.0` is unchanged and `1.6` is very bright. |
| `MIN_BRIGHTNESS` | `0.08` | Lowest brightness for any scene that isn't black, so dark scenes still glow a little. |
| `CONTRAST` | `1.20` | Extra contrast. `1.0` is unchanged. |
| `DARK_THRESHOLD` | `10` | Ignore screen areas whose R+G+B is below this, such as black bars around a movie. |
| `BLACK_SCREEN_THRESHOLD` | `8` | If the whole screen is darker than this, the lights fade to off. |

### Capture

| Setting | Default | Meaning |
| --- | --- | --- |
| `CAPTURE_MODE` | `"auto"` | `"auto"` uses the GPU pipeline and falls back to the CPU one if it fails. `"gpu"` and `"cpu"` force one pipeline. |
| `CURSOR_MODE` | `1` | `1` hides the mouse cursor in the capture. `2` includes it. |
| `SAMPLE_COLUMNS`, `SAMPLE_ROWS` | `32`, `18` | The screen is shrunk to this many pixels before its color is measured. Keep the screen's shape, for example 16×9 or 64×36. |
| `RESTART_DELAY` | `1.0` | Seconds to wait before rebuilding a capture pipeline after an error. |
| `STALL_WARNING` | `10.0` | Print a message if a screen sends no frames for this many seconds. |

### Tuning tips

* **Lights lag behind the screen:** raise `SMOOTHING` (for example `0.5`) or lower `UPDATE_INTERVAL`.
* **Lights flicker or jump:** lower `SMOOTHING` (for example `0.1`) or raise `COLOR_THRESHOLD` (for example `5`).
* **Colors look washed out:** raise `SATURATION_BOOST`.
* **Lights too dim:** raise `BRIGHTNESS_BOOST` or `MIN_BRIGHTNESS`.
* **Lights go off in dark scenes:** lower `BLACK_SCREEN_THRESHOLD`.

---

## How it works

```text
Screen ──► GNOME screen-sharing portal ──► PipeWire
       ──► GStreamer: shrink screen to 32×18 pixels (on the GPU)
       ──► Python: average the pixels, skipping near-black ones
       ──► boost saturation / brightness / contrast
       ──► smooth the change
       ──► same RGB color sent over UDP to every light in the room
```

1. **Capture.** AmbiWiz asks GNOME for permission to record the screen. GNOME delivers the frames through PipeWire.
2. **Shrink.** GStreamer scales each frame down to `SAMPLE_COLUMNS × SAMPLE_ROWS`, so each tiny pixel is the average of a patch of screen. With the GPU pipeline this happens on the graphics card, and only about 2 KB per frame is copied to the CPU.
3. **Measure.** The near-black pixels are dropped and the rest are averaged into one color. With several screens, their colors are averaged too.
4. **Enhance and smooth.** The color is made more vivid and brighter, then eased toward the new value so changes look smooth.
5. **Send.** If the color changed enough, a WiZ `setPilot` command goes to every light in the room over UDP:

   ```json
   {"method": "setPilot", "params": {"state": true, "r": 255, "g": 80, "b": 0}}
   ```

If a capture pipeline fails, AmbiWiz rebuilds it after `RESTART_DELAY` seconds.

---

## Troubleshooting

### Fullscreen windows

When a window goes fullscreen, GNOME can send it straight to the display and skip its usual compositing. During that time, screen capture only delivers frames in GPU memory. The GPU pipeline handles this, which is why AmbiWiz defaults to it.

If the lights freeze whenever something is fullscreen and resume when you leave fullscreen:

1. Check the startup output. It should say `capturing with GPU pipeline`.
2. If it says `falling back to CPU capture`, the error printed just before it gives the reason. Make sure `gstreamer1.0-gl` is installed (`sudo ./install-dependencies.sh`).
3. Make sure `CAPTURE_MODE` is not set to `"cpu"`.

### "no new frames for 10s"

GNOME only sends a new frame when something on the screen changes, so this message is normal on a still desktop. It means something is wrong only if it appears while the screen is clearly moving. In that case, see [Fullscreen windows](#fullscreen-windows).

### `ERROR starting screen capture`

You probably clicked **Cancel** in the sharing dialog, or the session isn't Wayland. Check:

```bash
echo "$XDG_SESSION_TYPE"                       # should print: wayland
systemctl --user status pipewire wireplumber
systemctl --user status xdg-desktop-portal xdg-desktop-portal-gnome
```

If a service isn't running, log out and back in, or reboot.

### `WiZ inventory file not found`

Run `python3 wiz_scanner.py` first. It writes `wiz_lights.json` next to the scripts.

### `No lights found in WiZ room ...`

`WIZ_ROOM_ID` doesn't match any room in `wiz_lights.json`. Run the scanner again and copy a room number from its output.

### The scanner finds no lights

* `NETWORK` in `wiz_scanner.py` doesn't match your network (see [Step 2](#step-2-find-your-lights)).
* The lights are switched off at the wall.
* The router isolates Wi-Fi devices from each other ("client isolation" or "AP isolation"), or a firewall blocks UDP port 38899.

### The lights don't react

* Check that the computer can reach a light, for example with `ping 10.0.0.50`.
* A light's IP address may have changed. Run the scanner again.
* Local control may be turned off for the lights in the WiZ app. Look under **Settings → Security → Allow local communication**.

### Python can't load D-Bus or GStreamer

```bash
python3 -c "import dbus; print('D-Bus OK')"
python3 -c "import gi; gi.require_version('Gst','1.0'); gi.require_version('GstVideo','1.0'); from gi.repository import Gst, GstVideo; print('GStreamer OK')"
```

If either command fails, run `sudo ./install-dependencies.sh` again.

---

## Running at login (optional)

You can start AmbiWiz automatically as a user service. GNOME still shows the screen-sharing dialog every time it starts, so you have to click **Share** after each login.

Create `~/.config/systemd/user/ambiwiz.service`:

```ini
[Unit]
Description=AmbiWiz ambient lighting
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/AmbiWiz/ambiwiz.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
```

Replace `/path/to/AmbiWiz/ambiwiz.py` with the real path, or point it at your `ambiwiz_local.py`. Then run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now ambiwiz.service
journalctl --user -u ambiwiz.service -f   # live log
```

To stop it, run `systemctl --user stop ambiwiz.service`. To stop it starting at login, run `systemctl --user disable ambiwiz.service`.

---

## Files

| File | Purpose |
| --- | --- |
| `ambiwiz.py` | The ambient lighting program. |
| `wiz_scanner.py` | Finds WiZ lights on your network and writes `wiz_lights.json`. |
| `wiz_lights.json` | Lights and rooms found by the scanner. Not tracked by git. Delete it and scan again to refresh. |
| `install-dependencies.sh` | Installs and checks the system packages. |

## Limitations

* GNOME on Wayland only.
* One zone: all lights in the chosen room show the same color.
* The screen-sharing dialog appears on every start.
* Rooms are shown as numbers, because the lights don't report room names.
* Settings are edited in the Python file. There is no settings window.

## Privacy

Screen frames are processed in memory on your computer and thrown away straight after. Only the resulting RGB values are sent, and only to the lights on your local network.

## License

No license has been chosen yet. Add one, such as MIT or GPL-3.0, before distributing the project.
