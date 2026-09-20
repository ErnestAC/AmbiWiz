#!/usr/bin/env python3

import ipaddress
import json
import os
import socket
import sys
import time


# ============================================================
# CONFIGURATION
# ============================================================

WIZ_PORT = 38899

OUTPUT_FILE = os.path.expanduser(
    "~/amb/wiz_lights.json"
)

# Change this if your LAN is different.
NETWORK = "192.168.0.0/24"

TIMEOUT = 0.5


# ============================================================
# WIZ QUERY
# ============================================================

QUERY = {
    "method": "getSystemConfig",
    "params": {},
}


def query_light(ip):
    """Ask one IP for its WiZ system configuration."""

    data = json.dumps(
        QUERY
    ).encode("utf-8")

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    sock.settimeout(
        TIMEOUT
    )

    try:

        sock.sendto(
            data,
            (
                str(ip),
                WIZ_PORT,
            ),
        )

        response, _ = sock.recvfrom(
            4096
        )

        result = json.loads(
            response.decode(
                "utf-8",
                errors="replace",
            )
        )

        if (
            result.get("method")
            != "getSystemConfig"
        ):
            return None

        if "result" not in result:
            return None

        config = result["result"]

        if "roomId" not in config:
            return None

        return config

    except (
        socket.timeout,
        OSError,
        json.JSONDecodeError,
    ):

        return None

    finally:

        sock.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print(" WiZ Light Discovery")
    print("==========================================")
    print()

    print(
        f"Scanning {NETWORK}..."
    )

    print()

    network = ipaddress.ip_network(
        NETWORK,
        strict=False,
    )

    lights = []

    total = network.num_addresses

    for index, ip in enumerate(
        network.hosts(),
        start=1,
    ):

        print(
            f"\rChecking {ip} "
            f"({index}/{total - 2})",
            end="",
            flush=True,
        )

        config = query_light(
            ip
        )

        if config is None:
            continue

        light = {
            "ip": str(ip),

            "mac": config.get(
                "mac"
            ),

            "room_id": config.get(
                "roomId"
            ),

            "home_id": config.get(
                "homeId"
            ),

            "module": config.get(
                "moduleName"
            ),

            "firmware": config.get(
                "fwVersion"
            ),

            "region": config.get(
                "rgn"
            ),
        }

        lights.append(
            light
        )

    print()
    print()

    # Sort consistently by room and IP.
    lights.sort(
        key=lambda light: (
            str(light["room_id"]),
            tuple(
                int(part)
                for part in light["ip"].split(".")
            ),
        )
    )

    # --------------------------------------------------------
    # Build room groups.
    # --------------------------------------------------------

    rooms = {}

    for light in lights:

        room_id = str(
            light["room_id"]
        )

        if room_id not in rooms:

            rooms[room_id] = {
                "room_id": int(
                    light["room_id"]
                ),

                # WiZ's local getSystemConfig API does not
                # provide the human-readable room name.
                #
                # You can fill this in manually later.
                "name": "",

                "lights": [],
            }

        rooms[room_id][
            "lights"
        ].append(
            light
        )

    # --------------------------------------------------------
    # Build final JSON.
    # --------------------------------------------------------

    output = {
        "generated": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "network": NETWORK,

        "lights": lights,

        "rooms": list(
            rooms.values()
        ),
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=4,
        )

        file.write(
            "\n"
        )

    # --------------------------------------------------------
    # Display results.
    # --------------------------------------------------------

    print(
        f"Found {len(lights)} WiZ device(s)."
    )

    print()

    if not rooms:

        print(
            "No WiZ lights were found."
        )

        return

    print(
        "Rooms:"
    )

    print()

    for room_id, room in rooms.items():

        print(
            f"Room {room_id}: "
            f"{len(room['lights'])} light(s)"
        )

        for light in room["lights"]:

            print(
                f"    {light['ip']}  "
                f"{light['module']}  "
                f"MAC={light['mac']}"
            )

        print()

    print(
        f"JSON written to:"
    )

    print(
        f"  {OUTPUT_FILE}"
    )

    print()


if __name__ == "__main__":
    main()
