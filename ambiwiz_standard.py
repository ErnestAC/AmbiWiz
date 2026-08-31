#!/usr/bin/env python3

import json
import os
import socket
import sys
import threading
import time

import dbus
import dbus.mainloop.glib
import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst


# ============================================================
# CONFIGURATION
# ============================================================

LEFT_LIGHT = "10.0.0.153" ## CHANGE THIS TO YOUR LEFT LIGHT IP
RIGHT_LIGHT = "10.0.0.50" ## CHANGE THIS TO YOUR RIGHT LIGHT IP

WIZ_PORT = 38899

# How often the lights are updated.
UPDATE_INTERVAL = 0.05

# Higher = smoother/slower transitions.
SMOOTHING = 0.15

# Ignore tiny color changes.
COLOR_THRESHOLD = 0

# Ignore black pixels.
DARK_THRESHOLD = 10

CURSOR_MODE = 2

# Screen sampling density.
SAMPLE_COLUMNS = 32
SAMPLE_ROWS = 18


# ============================================================
# GLOBAL STATE
# ============================================================

streams = []
streams_lock = threading.Lock()

left_color = [0.0, 0.0, 0.0]
right_color = [0.0, 0.0, 0.0]

last_left_sent = [-100, -100, -100]
last_right_sent = [-100, -100, -100]


# ============================================================
# UTILITY
# ============================================================

def clamp_rgb(values):
    """Convert RGB values to valid 0-255 integer values."""

    return tuple(
        max(0, min(255, round(value)))
        for value in values
    )


def color_changed(old, new):
    """Return True when any RGB channel changed enough to matter."""

    return any(
        abs(old[index] - new[index]) >= COLOR_THRESHOLD
        for index in range(3)
    )


def average_colors(colors):
    """Average a list of RGB tuples."""

    if not colors:
        return (0.0, 0.0, 0.0)

    count = len(colors)

    return tuple(
        sum(color[channel] for color in colors) / count
        for channel in range(3)
    )


# ============================================================
# WIZ CONTROL
# ============================================================

def send_wiz_color(ip, rgb):
    """Send an RGB color to a WiZ light over UDP."""

    command = {
        "method": "setPilot",
        "params": {
            "state": True,
            "r": int(rgb[0]),
            "g": int(rgb[1]),
            "b": int(rgb[2]),
        },
    }

    data = json.dumps(command).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.sendto(data, (ip, WIZ_PORT))

    except OSError as error:
        print(
            f"WiZ error ({ip}): {error}",
            flush=True,
        )

    finally:
        sock.close()


# ============================================================
# SCREEN COLOR ANALYSIS
# ============================================================

def calculate_stream_color(stream):
    """
    Calculate the average visible RGB color of one captured stream.

    Frames are copied while holding the stream lock, then analyzed
    without the lock so frame processing does not block GStreamer.
    """

    with stream["lock"]:
        frame = stream.get("frame")

        if frame is None:
            return None

        width = stream["width"]
        height = stream["height"]

        data = bytes(frame)

    if width <= 0 or height <= 0:
        return None

    step_x = max(1, width // SAMPLE_COLUMNS)
    step_y = max(1, height // SAMPLE_ROWS)

    total_r = 0
    total_g = 0
    total_b = 0
    count = 0

    stride = width * 4
    data_length = len(data)

    for y in range(0, height, step_y):
        row_offset = y * stride

        for x in range(0, width, step_x):
            offset = row_offset + (x * 4)

            if offset + 3 >= data_length:
                continue

            r = data[offset]
            g = data[offset + 1]
            b = data[offset + 2]

            # Ignore almost-black pixels.
            if r + g + b < DARK_THRESHOLD:
                continue

            total_r += r
            total_g += g
            total_b += b
            count += 1

    if count == 0:
        return (0.0, 0.0, 0.0)

    return (
        total_r / count,
        total_g / count,
        total_b / count,
    )


def get_desktop_bounds():
    """Return the horizontal bounds of all captured screens."""

    with streams_lock:
        if not streams:
            return (0, 0)

        min_x = min(
            stream.get("x", 0)
            for stream in streams
        )

        max_x = max(
            stream.get("x", 0)
            + stream.get(
                "position_width",
                stream.get("width", 0),
            )
            for stream in streams
        )

    return min_x, max_x


def calculate_ambient_colors():
    """
    Calculate average colors for the left and right sides
    of the desktop.
    """

    with streams_lock:
        current_streams = tuple(streams)

    min_x, max_x = get_desktop_bounds()
    desktop_center = (min_x + max_x) / 2

    left_values = []
    right_values = []

    for stream in current_streams:
        color = calculate_stream_color(stream)

        if color is None:
            continue

        stream_x = stream.get("x", 0)

        stream_width = stream.get(
            "position_width",
            stream.get("width", 0),
        )

        stream_center = stream_x + (stream_width / 2)

        if stream_center < desktop_center:
            left_values.append(color)
        else:
            right_values.append(color)

    return (
        average_colors(left_values),
        average_colors(right_values),
    )


# ============================================================
# LIGHT UPDATE
# ============================================================

def smooth_color(current, target):
    """Move a color toward its target using the configured smoothing."""

    for channel in range(3):
        current[channel] += (
            target[channel] - current[channel]
        ) * SMOOTHING


def update_lights():
    """
    Calculate the current ambient colors, smooth them, and update
    the WiZ lights when the color has changed enough.

    NOTE:
    The existing behavior is intentionally preserved:
    both lights receive right_rgb.
    """

    global last_left_sent
    global last_right_sent

    try:
        left_target, right_target = calculate_ambient_colors()

        smooth_color(left_color, left_target)
        smooth_color(right_color, right_target)

        left_rgb = clamp_rgb(left_color)
        right_rgb = clamp_rgb(right_color)

        # ----------------------------------------------------
        # Preserve existing behavior exactly.
        #
        # The original script compares last_right_sent here
        # and sends right_rgb to the LEFT light.
        # ----------------------------------------------------

        if color_changed(last_right_sent, right_rgb):
            send_wiz_color(
                LEFT_LIGHT,
                right_rgb, # change this to left_rgb if you want the left light to reflect the left side of the screen
            )

            last_left_sent = list(left_rgb)

        # ----------------------------------------------------
        # The original script also compares last_right_sent
        # here and sends right_rgb to the RIGHT light.
        # ----------------------------------------------------

        if color_changed(last_right_sent, right_rgb):
            send_wiz_color(
                RIGHT_LIGHT,
                right_rgb,
            )

            last_right_sent = list(right_rgb)

    except Exception as error:
        print(
            f"Color processing error: {error}",
            flush=True,
        )

    return True


# ============================================================
# GSTREAMER FRAME CALLBACK
# ============================================================

def on_new_sample(sink, stream):
    """Receive the latest GStreamer frame for a stream."""

    sample = sink.emit("pull-sample")

    if sample is None:
        return Gst.FlowReturn.ERROR

    buffer = sample.get_buffer()
    caps = sample.get_caps()
    structure = caps.get_structure(0)

    width = structure.get_value("width")
    height = structure.get_value("height")

    success, map_info = buffer.map(
        Gst.MapFlags.READ
    )

    if not success:
        return Gst.FlowReturn.ERROR

    try:
        frame = bytes(map_info.data)

        with stream["lock"]:
            stream["frame"] = frame
            stream["width"] = width
            stream["height"] = height

    finally:
        buffer.unmap(map_info)

    return Gst.FlowReturn.OK


# ============================================================
# GSTREAMER PIPELINE
# ============================================================

def create_stream(pipewire_fd, node_id, position, size):
    """Create and start one PipeWire → GStreamer capture pipeline."""

    pipeline = Gst.Pipeline.new(None)

    source = Gst.ElementFactory.make(
        "pipewiresrc",
        None,
    )

    convert = Gst.ElementFactory.make(
        "videoconvert",
        None,
    )

    capsfilter = Gst.ElementFactory.make(
        "capsfilter",
        None,
    )

    sink = Gst.ElementFactory.make(
        "appsink",
        None,
    )

    if not all([
        pipeline,
        source,
        convert,
        capsfilter,
        sink,
    ]):
        raise RuntimeError(
            "Could not create GStreamer elements."
        )

    # Duplicate the PipeWire descriptor for this stream.
    fd = os.dup(pipewire_fd)

    source.set_property(
        "fd",
        fd,
    )

    source.set_property(
        "path",
        str(node_id),
    )

    capsfilter.set_property(
        "caps",
        Gst.Caps.from_string(
            "video/x-raw,format=RGBA"
        ),
    )

    sink.set_property(
        "emit-signals",
        True,
    )

    sink.set_property(
        "max-buffers",
        1,
    )

    sink.set_property(
        "drop",
        True,
    )

    sink.set_property(
        "sync",
        False,
    )

    stream = {
        "pipeline": pipeline,
        "lock": threading.Lock(),

        "frame": None,

        "width": 0,
        "height": 0,

        "x": 0,
        "y": 0,

        "position_width": 0,
        "position_height": 0,
    }

    if position is not None:
        try:
            stream["x"] = int(position[0])
            stream["y"] = int(position[1])
        except Exception:
            pass

    if size is not None:
        try:
            stream["position_width"] = int(size[0])
            stream["position_height"] = int(size[1])
        except Exception:
            pass

    sink.connect(
        "new-sample",
        on_new_sample,
        stream,
    )

    pipeline.add(source)
    pipeline.add(convert)
    pipeline.add(capsfilter)
    pipeline.add(sink)

    if not source.link(convert):
        raise RuntimeError(
            "Could not link PipeWire source."
        )

    if not convert.link(capsfilter):
        raise RuntimeError(
            "Could not link videoconvert."
        )

    if not capsfilter.link(sink):
        raise RuntimeError(
            "Could not link capsfilter."
        )

    result = pipeline.set_state(
        Gst.State.PLAYING
    )

    if result == Gst.StateChangeReturn.FAILURE:
        raise RuntimeError(
            "Could not start GStreamer pipeline."
        )

    return stream


# ============================================================
# PORTAL REQUEST
# ============================================================

class PortalRequest:
    """Wait for an asynchronous ScreenCast portal request."""

    def __init__(self, bus, path):
        self.event = threading.Event()
        self.response_code = None
        self.results = None

        self.bus = bus
        self.path = path

        self.bus.add_signal_receiver(
            self._response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=self.path,
        )

    def _response(self, response, results):
        self.response_code = int(response)
        self.results = results
        self.event.set()


def dbus_main_iteration():
    """Process pending GLib/DBus events."""

    context = GLib.MainContext.default()

    while context.pending():
        context.iteration(False)


def wait_for_request(request):
    """Wait until a portal request completes."""

    while not request.event.wait(0.05):
        dbus_main_iteration()

    if request.response_code != 0:
        raise RuntimeError(
            "Portal request failed with response code "
            f"{request.response_code}"
        )

    return request.results


# ============================================================
# GNOME SCREENCAST PORTAL
# ============================================================

def start_portal_capture():
    """Create a GNOME ScreenCast session and open its PipeWire FD."""

    bus = dbus.SessionBus()

    portal_object = bus.get_object(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
    )

    screencast = dbus.Interface(
        portal_object,
        "org.freedesktop.portal.ScreenCast",
    )

    session_token = (
        "wizamb"
        + str(
            int(
                time.time() * 1_000_000
            )
        )
    )

    create_options = {
        "handle_token": dbus.String(session_token),
        "session_handle_token": dbus.String(session_token),
    }

    request_path = screencast.CreateSession(
        dbus.Dictionary(
            create_options,
            signature="sv",
        )
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    results = wait_for_request(request)

    session_handle = results["session_handle"]

    print(
        "Portal session created.",
        flush=True,
    )

    select_options = {
        "types": dbus.UInt32(1),
        "multiple": dbus.Boolean(True),
        "cursor_mode": dbus.UInt32(CURSOR_MODE),
    }

    request_path = screencast.SelectSources(
        session_handle,
        dbus.Dictionary(
            select_options,
            signature="sv",
        )
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    wait_for_request(request)

    print(
        "Screen source selected.",
        flush=True,
    )

    request_path = screencast.Start(
        session_handle,
        "",
        dbus.Dictionary(
            {},
            signature="sv",
        )
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    results = wait_for_request(request)

    streams_result = results["streams"]

    print(
        "Portal returned "
        f"{len(streams_result)} "
        "screen stream(s).",
        flush=True,
    )

    pipewire_fd = screencast.OpenPipeWireRemote(
        session_handle,
        dbus.Dictionary(
            {},
            signature="sv",
        )
    )

    # OpenPipeWireRemote returns dbus.UnixFd.
    #
    # dbus-python on this system does not expose UnixFd
    # as dbus.UnixFd. The returned object provides take(),
    # which extracts the actual Linux file descriptor.

    if hasattr(pipewire_fd, "take"):
        pipewire_fd = pipewire_fd.take()
    else:
        pipewire_fd = int(pipewire_fd)

    print(
        "PipeWire connection opened "
        f"(fd={pipewire_fd}).",
        flush=True,
    )

    return (
        bus,
        screencast,
        session_handle,
        pipewire_fd,
        streams_result,
    )


# ============================================================
# CLEANUP
# ============================================================

def stop_streams():
    """Stop all active GStreamer pipelines."""

    with streams_lock:
        current_streams = tuple(streams)

    for stream in current_streams:
        try:
            stream["pipeline"].set_state(
                Gst.State.NULL
            )
        except Exception:
            pass


def close_fd(fd):
    """Safely close a file descriptor."""

    try:
        os.close(fd)
    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print(" WiZ Wayland Ambilight")
    print("==========================================")
    print()

    print(f"LEFT  → {LEFT_LIGHT}")
    print(f"RIGHT → {RIGHT_LIGHT}")

    print()

    print(
        "Capture: GNOME ScreenCast / PipeWire"
    )

    print()

    Gst.init(None)

    try:
        (
            bus,
            screencast,
            session_handle,
            pipewire_fd,
            stream_info,
        ) = start_portal_capture()

    except Exception as error:
        print()
        print("ERROR starting screen capture:")
        print(error)
        print()
        sys.exit(1)

    for item in stream_info:

        node_id = int(item[0])
        properties = item[1]

        position = None
        size = None

        try:
            if "position" in properties:
                position = tuple(
                    properties["position"]
                )
        except Exception:
            pass

        try:
            if "size" in properties:
                size = tuple(
                    properties["size"]
                )
        except Exception:
            pass

        print(
            f"Screen stream: "
            f"node={node_id} "
            f"position={position} "
            f"size={size}",
            flush=True,
        )

        try:
            stream = create_stream(
                pipewire_fd,
                node_id,
                position,
                size,
            )

            with streams_lock:
                streams.append(stream)

        except Exception as error:
            print(
                f"ERROR creating stream "
                f"{node_id}: {error}",
                flush=True,
            )

    if not streams:
        print()
        print(
            "ERROR: No GStreamer "
            "screen streams were created."
        )

        close_fd(pipewire_fd)
        sys.exit(1)

    print()

    print("Ambilight is running.")
    print(f"Left light : {LEFT_LIGHT}")
    print(f"Right light: {RIGHT_LIGHT}")

    print()

    print("Press Ctrl+C to stop.")
    print()

    main_loop = GLib.MainLoop()

    GLib.timeout_add(
        int(UPDATE_INTERVAL * 1000),
        update_lights,
    )

    try:
        main_loop.run()

    except KeyboardInterrupt:
        print()
        print("Stopping Ambilight...")

    finally:
        stop_streams()

        try:
            screencast.Stop(
                session_handle,
                dbus.Dictionary(
                    {},
                    signature="sv",
                )
            )
        except Exception:
            pass

        close_fd(pipewire_fd)

        print("Ambilight stopped.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    dbus.mainloop.glib.DBusGMainLoop(
        set_as_default=True
    )

    main()

