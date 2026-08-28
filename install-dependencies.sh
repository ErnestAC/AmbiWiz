```bash
#!/usr/bin/env bash

set -e

echo
echo "=========================================="
echo " WiZ Wayland AmbiWiz"
echo " Dependency Installer"
echo "=========================================="
echo

# ------------------------------------------------------------
# Require root
# ------------------------------------------------------------

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: This installer must be run with sudo."
    echo
    echo "Run:"
    echo "  sudo ./install-dependencies.sh"
    echo
    exit 1
fi

# ------------------------------------------------------------
# Update package lists
# ------------------------------------------------------------

echo "Updating package lists..."
apt update

echo

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------

echo "Installing required packages..."

apt install -y \
    python3 \
    python3-dbus \
    python3-gi \
    gir1.2-gstreamer-1.0 \
    gstreamer1.0-pipewire \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    pipewire \
    wireplumber \
    xdg-desktop-portal \
    xdg-desktop-portal-gnome

echo

# ------------------------------------------------------------
# Verify Python D-Bus
# ------------------------------------------------------------

echo "Checking Python D-Bus..."

if python3 -c "import dbus" 2>/dev/null; then
    echo "  OK: python3-dbus"
else
    echo "  ERROR: Python D-Bus is not available."
    exit 1
fi

# ------------------------------------------------------------
# Verify GStreamer Python bindings
# ------------------------------------------------------------

echo "Checking GStreamer Python bindings..."

if python3 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst" 2>/dev/null; then
    echo "  OK: GStreamer Python bindings"
else
    echo "  ERROR: GStreamer Python bindings are not available."
    exit 1
fi

# ------------------------------------------------------------
# Verify GStreamer elements
# ------------------------------------------------------------

echo "Checking GStreamer elements..."

check_gst_element() {
    local element="$1"

    if gst-inspect-1.0 "$element" >/dev/null 2>&1; then
        echo "  OK: $element"
    else
        echo "  ERROR: $element not found."
        return 1
    fi
}

check_gst_element pipewiresrc
check_gst_element videoconvert
check_gst_element capsfilter
check_gst_element appsink

# ------------------------------------------------------------
# Check PipeWire
# ------------------------------------------------------------

echo
echo "Checking PipeWire..."

if command -v pipewire >/dev/null 2>&1; then
    echo "  OK: PipeWire installed"
else
    echo "  ERROR: PipeWire executable not found."
    exit 1
fi

# ------------------------------------------------------------
# Check WirePlumber
# ------------------------------------------------------------

echo "Checking WirePlumber..."

if command -v wireplumber >/dev/null 2>&1; then
    echo "  OK: WirePlumber installed"
else
    echo "  ERROR: WirePlumber executable not found."
    exit 1
fi

# ------------------------------------------------------------
# Check desktop portal
# ------------------------------------------------------------

echo "Checking GNOME ScreenCast portal..."

if command -v xdg-desktop-portal >/dev/null 2>&1; then
    echo "  OK: xdg-desktop-portal installed"
else
    echo "  ERROR: xdg-desktop-portal not found."
    exit 1
fi

if dpkg -s xdg-desktop-portal-gnome >/dev/null 2>&1; then
    echo "  OK: xdg-desktop-portal-gnome installed"
else
    echo "  ERROR: GNOME portal backend not found."
    exit 1
fi

# ------------------------------------------------------------
# Installation complete
# ------------------------------------------------------------

echo
echo "=========================================="
echo " Dependencies installed successfully!"
echo "=========================================="
echo

echo "The AmbiWiz script can now be run with:"
echo
echo "  ./ambiwiz.py"
echo

echo "If this is the first installation, log out and"
echo "back in if GNOME/PipeWire services do not appear"
echo "to be running correctly."
echo
```