#!/usr/bin/env python3

import colorsys
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
gi.require_version("GstVideo", "1.0")
from gi.repository import GLib, Gst, GstVideo


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# WIZ LIGHTS
# ------------------------------------------------------------

WIZ_INVENTORY_FILE = os.path.expanduser(
    "wiz_lights.json"
)

# Select the WiZ room to control. - Use wiz_scanner.py to find the room ID.

WIZ_ROOM_ID = 9999999 # Living Room

WIZ_LIGHTS = []

WIZ_PORT = 38899


# ------------------------------------------------------------
# UPDATE / RESPONSE
# ------------------------------------------------------------

# 0.05 = 20 updates per second.
UPDATE_INTERVAL = 0.05

# How quickly the lights follow the screen.
#
# Higher = faster response.
# Lower  = smoother response.
SMOOTHING = 0.25


# ------------------------------------------------------------
# COLOR PROCESSING
# ------------------------------------------------------------

# Ignore extremely small changes.
COLOR_THRESHOLD = 2

# Pixels below this combined RGB value are ignored when
# calculating the screen color.
DARK_THRESHOLD = 10

# Increase color saturation.
#
# 1.0 = original
# 1.3 = noticeable
# 1.6 = vivid
# 2.0 = very strong
SATURATION_BOOST = 1.60

# Increase perceived brightness.
#
# 1.0 = original
# 1.20 = noticeable
# 1.40 = bright
# 1.60 = very bright
BRIGHTNESS_BOOST = 1.35

# Minimum brightness for non-black scenes.
#
# This keeps the ambient lights visible when the screen is
# dark, while still allowing a completely black screen to
# turn the lights off.
MIN_BRIGHTNESS = 0.08

# Additional contrast.
#
# 1.0 = normal
# >1.0 = stronger
CONTRAST = 1.20

# If the average screen brightness is below this value,
# treat the entire screen as black.
BLACK_SCREEN_THRESHOLD = 8


# ------------------------------------------------------------
# SCREEN CAPTURE
# ------------------------------------------------------------

# 2 = do not capture the mouse cursor.
CURSOR_MODE = 1

# Capture pipeline.
#
# "auto" = GPU pipeline, falls back to CPU if it fails.
#          Recommended: needed for fullscreen apps.
# "gpu"  = GPU pipeline only (OpenGL + DMA-BUF).
# "cpu"  = CPU pipeline only. Fullscreen windows may freeze
#          the lights until they leave fullscreen.
CAPTURE_MODE = "auto"

# Seconds to wait before rebuilding a failed pipeline.
RESTART_DELAY = 1.0

# Report a stream that sends no frames for this many
# seconds. A still screen also sends no frames.
STALL_WARNING = 10.0

# Screen sampling density. The screen is scaled down to
# this many pixels and each one is used.
SAMPLE_COLUMNS = 32
SAMPLE_ROWS = 18


# ============================================================
# GLOBAL STATE
# ============================================================

streams = []
streams_lock = threading.Lock()

# ONE shared color for the entire illumination zone.
ambient_color = [0.0, 0.0, 0.0]

# Last RGB value actually sent to the lights.
last_sent_color = [-100, -100, -100]


# ============================================================
# UTILITY
# ============================================================

def clamp(
    value,
    minimum=0.0,
    maximum=255.0,
):
    """Clamp a value to a specified range."""

    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def clamp_rgb(values):
    """Convert RGB values to valid 0-255 integers."""

    return tuple(
        int(
            round(
                clamp(value)
            )
        )
        for value in values
    )


def color_changed(old, new):
    """
    Return True if the RGB color changed enough to justify
    another WiZ update.
    """

    return any(
        abs(
            old[index]
            - new[index]
        ) >= COLOR_THRESHOLD
        for index in range(3)
    )


# ============================================================
# COLOR ENHANCEMENT
# ============================================================

def enhance_color(rgb):
    """
    Make the ambient color more noticeable.

    Processing:

        RGB
          ↓
        HSV
          ↓
        Saturation boost
          ↓
        Brightness boost
          ↓
        Minimum brightness
          ↓
        Contrast
          ↓
        RGB
    """

    r, g, b = rgb

    # Normalize to 0-1.
    r /= 255.0
    g /= 255.0
    b /= 255.0

    # Convert RGB → HSV.
    h, s, v = colorsys.rgb_to_hsv(
        r,
        g,
        b,
    )

    # --------------------------------------------------------
    # Saturation
    # --------------------------------------------------------

    s *= SATURATION_BOOST

    s = max(
        0.0,
        min(
            1.0,
            s,
        ),
    )

    # --------------------------------------------------------
    # Brightness
    # --------------------------------------------------------

    v *= BRIGHTNESS_BOOST

    if v > 0.0:
        v = max(
            v,
            MIN_BRIGHTNESS,
        )

    v = max(
        0.0,
        min(
            1.0,
            v,
        ),
    )

    # HSV → RGB.
    r, g, b = colorsys.hsv_to_rgb(
        h,
        s,
        v,
    )

    # --------------------------------------------------------
    # Contrast
    # --------------------------------------------------------

    r = (
        (r - 0.5)
        * CONTRAST
    ) + 0.5

    g = (
        (g - 0.5)
        * CONTRAST
    ) + 0.5

    b = (
        (b - 0.5)
        * CONTRAST
    ) + 0.5

    r = max(
        0.0,
        min(
            1.0,
            r,
        ),
    )

    g = max(
        0.0,
        min(
            1.0,
            g,
        ),
    )

    b = max(
        0.0,
        min(
            1.0,
            b,
        ),
    )

    return (
        r * 255.0,
        g * 255.0,
        b * 255.0,
    )


# ============================================================
# SCREEN COLOR ANALYSIS
# ============================================================

def calculate_stream_color(stream):
    """
    Calculate the average visible RGB color of one captured
    screen stream.

    GStreamer has already scaled the frame down to
    SAMPLE_COLUMNS x SAMPLE_ROWS, so every pixel is already
    an average of a screen region. Each pixel is used here.

    The frame is copied while holding the stream lock and
    analyzed afterward.
    """

    with stream["lock"]:

        data = stream.get(
            "frame"
        )

        if data is None:
            return None

        width = stream["width"]
        height = stream["height"]
        stride = stream["stride"]

    if width <= 0 or height <= 0:
        return None

    if stride <= 0:
        stride = width * 4

    total_r = 0.0
    total_g = 0.0
    total_b = 0.0

    count = 0

    data_length = len(data)

    for y in range(height):

        row_offset = (
            y * stride
        )

        for x in range(width):

            offset = (
                row_offset
                + (x * 4)
            )

            if (
                offset + 3
                >= data_length
            ):
                break

            r = data[offset]
            g = data[offset + 1]
            b = data[offset + 2]

            # Ignore almost-black pixels.
            if (
                r + g + b
                < DARK_THRESHOLD
            ):
                continue

            total_r += r
            total_g += g
            total_b += b

            count += 1

    if count == 0:

        return (
            0.0,
            0.0,
            0.0,
        )

    return (
        total_r / count,
        total_g / count,
        total_b / count,
    )

def calculate_ambient_color():
    """
    Calculate ONE color for the entire desktop.

    All captured screen streams contribute to the same
    illumination zone.

    There is intentionally no left/right distinction.
    """

    with streams_lock:

        current_streams = tuple(
            streams
        )

    colors = []

    for stream in current_streams:

        color = calculate_stream_color(
            stream
        )

        if color is not None:

            colors.append(
                color
            )

    if not colors:

        return (
            0.0,
            0.0,
            0.0,
        )

    count = len(colors)

    return (
        sum(
            color[0]
            for color in colors
        ) / count,

        sum(
            color[1]
            for color in colors
        ) / count,

        sum(
            color[2]
            for color in colors
        ) / count,
    )


# ============================================================
# WIZ CONTROL
# ============================================================

def send_wiz_color(rgb):
    """
    Send the EXACT SAME RGB value to every light.

    All lights are treated as one illumination zone.
    """

    command = {
        "method": "setPilot",

        "params": {
            "state": True,

            "r": int(rgb[0]),
            "g": int(rgb[1]),
            "b": int(rgb[2]),
        },
    }

    data = json.dumps(
        command
    ).encode(
        "utf-8"
    )

    # Create sockets first so the two packets can be sent
    # as close together as possible.
    sockets = []

    try:

        for ip in WIZ_LIGHTS:

            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )

            sockets.append(
                (
                    ip,
                    sock,
                )
            )

        # Send the exact same packet to every light.
        for ip, sock in sockets:

            try:

                sock.sendto(
                    data,
                    (
                        ip,
                        WIZ_PORT,
                    ),
                )

            except OSError as error:

                print(
                    f"WiZ error ({ip}): {error}",
                    flush=True,
                )

    finally:

        for _, sock in sockets:

            try:
                sock.close()
            except Exception:
                pass


# ============================================================
# LIGHT UPDATE
# ============================================================

def smooth_color(
    current,
    target,
):
    """
    Smoothly move the current shared color toward the target.
    """

    for channel in range(3):

        current[channel] += (
            target[channel]
            - current[channel]
        ) * SMOOTHING


def update_lights():
    """
    Calculate ONE ambient color, enhance it, smooth it,
    and send that SAME RGB value to every WiZ light.
    """

    global last_sent_color

    try:

        # ----------------------------------------------------
        # Get one color from the entire desktop.
        # ----------------------------------------------------

        target_color = (
            calculate_ambient_color()
        )

        # ----------------------------------------------------
        # Determine whether the screen is effectively black.
        # ----------------------------------------------------

        screen_brightness = (
            target_color[0]
            + target_color[1]
            + target_color[2]
        ) / 3.0

        if (
            screen_brightness
            <= BLACK_SCREEN_THRESHOLD
        ):

            target_color = (
                0.0,
                0.0,
                0.0,
            )

        else:

            # Make the color more vivid and visible.
            target_color = enhance_color(
                target_color
            )

        # ----------------------------------------------------
        # Smooth the ONE shared color.
        # ----------------------------------------------------

        smooth_color(
            ambient_color,
            target_color,
        )

        # ----------------------------------------------------
        # Convert to actual WiZ RGB values.
        # ----------------------------------------------------

        rgb = clamp_rgb(
            ambient_color
        )

        # ----------------------------------------------------
        # Send only when the shared color changed enough.
        # ----------------------------------------------------

        if color_changed(
            last_sent_color,
            rgb,
        ):

            send_wiz_color(
                rgb
            )

            last_sent_color = list(
                rgb
            )

    except Exception as error:

        print(
            f"Color processing error: {error}",
            flush=True,
        )

    return True


# ============================================================
# GSTREAMER FRAME CALLBACK
# ============================================================

def on_new_sample(
    sink,
    stream,
    generation,
):
    """Receive the latest (already downscaled) frame."""

    sample = sink.emit(
        "pull-sample"
    )

    if sample is None:

        return Gst.FlowReturn.ERROR

    # Ignore frames from a pipeline that is being replaced.
    if generation != stream["generation"]:

        return Gst.FlowReturn.OK

    buffer = sample.get_buffer()

    caps = sample.get_caps()

    info = GstVideo.VideoInfo.new_from_caps(
        caps
    )

    if info is None:

        return Gst.FlowReturn.ERROR

    success, map_info = buffer.map(
        Gst.MapFlags.READ
    )

    if not success:

        return Gst.FlowReturn.ERROR

    try:

        frame = bytes(
            map_info.data
        )

    finally:

        buffer.unmap(
            map_info
        )

    with stream["lock"]:

        stream["frame"] = frame
        stream["width"] = info.width
        stream["height"] = info.height
        stream["stride"] = info.stride[0]

        stream["frame_count"] += 1
        stream["last_frame_time"] = time.monotonic()

    return Gst.FlowReturn.OK


# ============================================================
# GSTREAMER PIPELINE
# ============================================================

def pipeline_description(mode):
    """
    Return the GStreamer pipeline for a capture mode.

    gpu:
        Accepts DMA-BUF (GPU) frames from PipeWire, scales
        them down on the GPU and downloads only a tiny image.

        GNOME sends fullscreen windows straight to the
        display ("direct scanout"). While that happens,
        screen capture often only produces GPU buffers, so a
        CPU-only pipeline gets no new frames until the window
        leaves fullscreen.

    cpu:
        Memory-mapped frames only, scaled on the CPU.
        Fallback for systems without working OpenGL.
    """

    size = (
        f"width={SAMPLE_COLUMNS},"
        f"height={SAMPLE_ROWS}"
    )

    if mode == "gpu":

        return (
            "pipewiresrc name=src ! "
            "glupload ! "
            "glcolorconvert ! "
            "glcolorscale ! "
            "video/x-raw(memory:GLMemory),"
            f"format=RGBA,{size} ! "
            "gldownload ! "
            "video/x-raw,format=RGBA ! "
            "appsink name=sink"
        )

    return (
        "pipewiresrc name=src ! "
        "videoconvertscale add-borders=false ! "
        f"video/x-raw,format=RGBA,{size} ! "
        "appsink name=sink"
    )


def build_pipeline(stream, mode):
    """Create and start the pipeline for one stream."""

    stream["generation"] += 1
    generation = stream["generation"]

    pipeline = Gst.parse_launch(
        pipeline_description(mode)
    )

    source = pipeline.get_by_name(
        "src"
    )

    sink = pipeline.get_by_name(
        "sink"
    )

    # Duplicate the PipeWire descriptor. Every pipeline
    # gets its own copy, so rebuilding a pipeline never
    # closes the shared descriptor.
    source.set_property(
        "fd",
        os.dup(stream["pipewire_fd"]),
    )

    source.set_property(
        "path",
        str(stream["node_id"]),
    )

    sink.set_property("emit-signals", True)
    sink.set_property("max-buffers", 1)
    sink.set_property("drop", True)
    sink.set_property("sync", False)

    sink.connect(
        "new-sample",
        on_new_sample,
        stream,
        generation,
    )

    bus = pipeline.get_bus()

    bus.add_signal_watch()

    bus.connect(
        "message",
        on_bus_message,
        stream,
        generation,
    )

    stream["pipeline"] = pipeline
    stream["mode"] = mode
    stream["started_time"] = time.monotonic()

    with stream["lock"]:

        stream["frame_count"] = 0

    result = pipeline.set_state(
        Gst.State.PLAYING
    )

    if (
        result
        == Gst.StateChangeReturn.FAILURE
    ):

        raise RuntimeError(
            f"Could not start {mode} pipeline."
        )

    print(
        f"Stream {stream['node_id']}: "
        f"capturing with {mode.upper()} pipeline.",
        flush=True,
    )


def teardown_pipeline(stream):
    """Stop and release a stream's current pipeline."""

    pipeline = stream.get(
        "pipeline"
    )

    if pipeline is None:
        return

    stream["pipeline"] = None

    try:
        pipeline.get_bus().remove_signal_watch()
    except Exception:
        pass

    try:
        pipeline.set_state(
            Gst.State.NULL
        )
    except Exception:
        pass


def restart_stream(stream, mode):
    """Rebuild a stream's pipeline (runs on the main loop)."""

    stream["restart_pending"] = False

    teardown_pipeline(
        stream
    )

    try:

        build_pipeline(
            stream,
            mode,
        )

    except Exception as error:

        print(
            f"Stream {stream['node_id']}: "
            f"restart failed: {error}",
            flush=True,
        )

        schedule_restart(
            stream,
            "cpu",
            delay=RESTART_DELAY * 2,
        )

    # One-shot GLib timeout.
    return False


def schedule_restart(stream, mode, delay=None):
    """Rebuild a stream's pipeline after a short delay."""

    if stream["restart_pending"]:
        return

    stream["restart_pending"] = True

    # Stop the stream's current generation from
    # delivering frames or bus messages.
    stream["generation"] += 1

    GLib.timeout_add(
        int(
            (delay or RESTART_DELAY)
            * 1000
        ),
        restart_stream,
        stream,
        mode,
    )


def on_bus_message(bus, message, stream, generation):
    """Handle pipeline errors and end-of-stream."""

    if generation != stream["generation"]:
        return

    if message.type == Gst.MessageType.ERROR:

        error, debug = message.parse_error()

        print(
            f"Stream {stream['node_id']} "
            f"({stream['mode']}) error: "
            f"{error.message}",
            flush=True,
        )

        if debug:
            print(
                f"  {debug.splitlines()[0]}",
                flush=True,
            )

        with stream["lock"]:
            frames = stream["frame_count"]

        # The GPU pipeline failed before showing any frame:
        # OpenGL / DMA-BUF probably does not work here.
        # Fall back to the CPU pipeline for this stream.
        if (
            stream["mode"] == "gpu"
            and frames == 0
            and CAPTURE_MODE == "auto"
        ):

            print(
                f"Stream {stream['node_id']}: "
                "falling back to CPU capture.",
                flush=True,
            )

            schedule_restart(stream, "cpu")

        else:

            schedule_restart(stream, stream["mode"])

    elif message.type == Gst.MessageType.EOS:

        print(
            f"Stream {stream['node_id']}: "
            "end of stream, restarting.",
            flush=True,
        )

        schedule_restart(stream, stream["mode"])

    elif message.type == Gst.MessageType.WARNING:

        warning, _ = message.parse_warning()

        print(
            f"Stream {stream['node_id']} warning: "
            f"{warning.message}",
            flush=True,
        )


def check_streams():
    """
    Report streams that stop delivering frames.

    GNOME only sends a frame when the screen changes, so a
    still desktop can be quiet for a long time. A quiet stream
    is reported, but not restarted.
    """

    now = time.monotonic()

    with streams_lock:
        current_streams = tuple(streams)

    for stream in current_streams:

        with stream["lock"]:
            last = stream["last_frame_time"]

        since = stream.get("started_time") or now

        if last is not None:
            since = max(since, last)

        idle = now - since

        if idle >= STALL_WARNING and not stream["stalled"]:

            stream["stalled"] = True

            print(
                f"Stream {stream['node_id']} "
                f"({stream['mode']}): no new frames "
                f"for {idle:.0f}s.",
                flush=True,
            )

        elif idle < STALL_WARNING and stream["stalled"]:

            stream["stalled"] = False

            print(
                f"Stream {stream['node_id']}: "
                "frames are arriving again.",
                flush=True,
            )

    return True


def create_stream(
    pipewire_fd,
    node_id,
    position,
    size,
):
    """
    Create and start one PipeWire → GStreamer stream.
    """

    stream = {
        "pipeline": None,
        "pipewire_fd": pipewire_fd,
        "node_id": node_id,
        "mode": None,
        "generation": 0,
        "restart_pending": False,
        "started_time": None,
        "stalled": False,

        "lock": threading.Lock(),

        "frame": None,
        "frame_count": 0,
        "last_frame_time": None,

        "width": 0,
        "height": 0,
        "stride": 0,

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

    mode = (
        "cpu"
        if CAPTURE_MODE == "cpu"
        else "gpu"
    )

    try:

        build_pipeline(
            stream,
            mode,
        )

    except Exception as error:

        if mode == "cpu" or CAPTURE_MODE != "auto":
            raise

        print(
            f"Stream {node_id}: GPU pipeline unavailable "
            f"({error}), using CPU capture.",
            flush=True,
        )

        teardown_pipeline(stream)

        build_pipeline(
            stream,
            "cpu",
        )

    return stream

# ============================================================
# PORTAL REQUEST
# ============================================================

class PortalRequest:
    """Wait for an asynchronous ScreenCast portal request."""

    def __init__(
        self,
        bus,
        path,
    ):

        self.event = threading.Event()

        self.response_code = None
        self.results = None

        self.bus = bus
        self.path = path

        self.bus.add_signal_receiver(
            self._response,

            signal_name="Response",

            dbus_interface=(
                "org.freedesktop.portal.Request"
            ),

            path=self.path,
        )

    def _response(
        self,
        response,
        results,
    ):

        self.response_code = int(
            response
        )

        self.results = results

        self.event.set()


def dbus_main_iteration():
    """Process pending GLib/DBus events."""

    context = (
        GLib.MainContext.default()
    )

    while context.pending():

        context.iteration(
            False
        )


def wait_for_request(
    request
):
    """Wait until a portal request completes."""

    while not request.event.wait(
        0.05
    ):

        dbus_main_iteration()

    if request.response_code != 0:

        raise RuntimeError(
            "Portal request failed with "
            "response code "
            f"{request.response_code}"
        )

    return request.results


# ============================================================
# GNOME SCREENCAST PORTAL
# ============================================================

def start_portal_capture():
    """
    Create a GNOME ScreenCast session and open its PipeWire FD.
    """

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
                time.time()
                * 1_000_000
            )
        )
    )

    create_options = {

        "handle_token": dbus.String(
            session_token
        ),

        "session_handle_token": dbus.String(
            session_token
        ),
    }

    request_path = (
        screencast.CreateSession(
            dbus.Dictionary(
                create_options,
                signature="sv",
            )
        )
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    results = wait_for_request(
        request
    )

    session_handle = results[
        "session_handle"
    ]

    print(
        "Portal session created.",
        flush=True,
    )

    select_options = {

        "types": dbus.UInt32(
            1
        ),

        "multiple": dbus.Boolean(
            True
        ),

        "cursor_mode": dbus.UInt32(
            CURSOR_MODE
        ),
    }

    request_path = (
        screencast.SelectSources(
            session_handle,

            dbus.Dictionary(
                select_options,
                signature="sv",
            ),
        )
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    wait_for_request(
        request
    )

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
        ),
    )

    request = PortalRequest(
        bus,
        str(request_path),
    )

    results = wait_for_request(
        request
    )

    streams_result = results[
        "streams"
    ]

    print(
        "Portal returned "
        f"{len(streams_result)} "
        "screen stream(s).",
        flush=True,
    )

    pipewire_fd = (
        screencast.OpenPipeWireRemote(
            session_handle,

            dbus.Dictionary(
                {},
                signature="sv",
            ),
        )
    )

    # dbus-python on this system does not expose UnixFd as
    # dbus.UnixFd.
    #
    # The returned object provides take(), which extracts
    # the actual Linux file descriptor.

    if hasattr(
        pipewire_fd,
        "take",
    ):

        pipewire_fd = (
            pipewire_fd.take()
        )

    else:

        pipewire_fd = int(
            pipewire_fd
        )

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

        current_streams = tuple(
            streams
        )

    for stream in current_streams:

        teardown_pipeline(
            stream
        )


def close_fd(fd):
    """Safely close a file descriptor."""

    try:

        os.close(
            fd
        )

    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print(" AmbiWiz Enhanced")
    print("==========================================")
    print()
    load_wiz_room()
    print(
        "Illumination zone:"
    )

    for ip in WIZ_LIGHTS:

        print(
            f"  → {ip}"
        )

    print()

    print(
        "Both lights will always receive "
        "the same RGB value."
    )

    print()

    print(
        "Capture: GNOME ScreenCast / PipeWire"
    )

    print()

    print(
        "Color enhancement:"
    )

    print(
        f"  Saturation boost  : "
        f"{SATURATION_BOOST:.2f}x"
    )

    print(
        f"  Brightness boost  : "
        f"{BRIGHTNESS_BOOST:.2f}x"
    )

    print(
        f"  Minimum brightness: "
        f"{MIN_BRIGHTNESS:.2f}"
    )

    print(
        f"  Contrast          : "
        f"{CONTRAST:.2f}x"
    )

    print()

    Gst.init(
        None
    )

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

        print(
            "ERROR starting screen capture:"
        )

        print(
            error
        )

        print()

        sys.exit(
            1
        )

    for item in stream_info:

        node_id = int(
            item[0]
        )

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

                streams.append(
                    stream
                )

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

        close_fd(
            pipewire_fd
        )

        sys.exit(
            1
        )

    print()

    print(
        "AmbiWiz is running."
    )

    print(
        "Mode: Single illumination zone"
    )

    print(
        f"Lights: {len(WIZ_LIGHTS)}"
    )

    print()

    print(
        "Press Ctrl+C to stop."
    )

    print()

    main_loop = GLib.MainLoop()

    GLib.timeout_add(
        int(
            UPDATE_INTERVAL
            * 1000
        ),
        update_lights,
    )

    GLib.timeout_add_seconds(
        2,
        check_streams,
    )

    try:

        main_loop.run()

    except KeyboardInterrupt:

        print()

        print(
            "Stopping AmbiWiz..."
        )

    finally:

        stop_streams()

        try:

            screencast.Stop(
                session_handle,

                dbus.Dictionary(
                    {},
                    signature="sv",
                ),
            )

        except Exception:
            pass

        close_fd(
            pipewire_fd
        )

        print(
            "AmbiWiz stopped."
        )

def load_wiz_room():
    """
    Load the WiZ inventory and select all lights belonging
    to the configured room.
    """

    global WIZ_LIGHTS

    if not os.path.isfile(WIZ_INVENTORY_FILE):
        print()
        print("ERROR: WiZ inventory file not found:")
        print(f"  {WIZ_INVENTORY_FILE}")
        print()
        print("Run wiz_scanner.py first.")
        sys.exit(1)

    try:
        with open(
            WIZ_INVENTORY_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            inventory = json.load(f)

    except Exception as e:
        print()
        print("ERROR: Could not read WiZ inventory:")
        print(f"  {e}")
        sys.exit(1)

    selected = []

    for light in inventory.get("lights", []):
        try:
            light_room_id = int(
                light.get("room_id")
            )
        except (TypeError, ValueError):
            continue

        if light_room_id != int(WIZ_ROOM_ID):
            continue

        ip = light.get("ip")

        if ip and ip not in selected:
            selected.append(ip)

    if not selected:
        print()
        print(
            f"ERROR: No lights found in WiZ room "
            f"{WIZ_ROOM_ID}."
        )
        print(
            f"Inventory: {WIZ_INVENTORY_FILE}"
        )
        sys.exit(1)

    WIZ_LIGHTS = selected

    print()
    print("WiZ room selection")
    print("-------------------")
    print(f"Room ID: {WIZ_ROOM_ID}")
    print("Lights:")

    for ip in WIZ_LIGHTS:
        print(f"  {ip}")

    print()

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    dbus.mainloop.glib.DBusGMainLoop(
        set_as_default=True
    )

    main()
