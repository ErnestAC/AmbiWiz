#!/usr/bin/env python3

import concurrent.futures
import ipaddress
import json
import socket


# ============================================================
# CONFIGURATION
# ============================================================

# Change this to match the local network where your WiZ lights
# are located.
NETWORK = "192.168.1.0/24"

WIZ_PORT = 38899
TIMEOUT = 0.5
MAX_WORKERS = 50


# ============================================================
# WIZ COMMUNICATION
# ============================================================

def get_system_config(ip):
    request = {
        "method": "getSystemConfig",
        "params": {}
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    try:
        sock.sendto(
            json.dumps(request).encode("utf-8"),
            (str(ip), WIZ_PORT)
        )

        data, _ = sock.recvfrom(8192)
        response = json.loads(data.decode("utf-8"))

        if response.get("method") == "getSystemConfig":
            return response.get("result", {})

    except (
        socket.timeout,
        socket.error,
        json.JSONDecodeError,
        UnicodeDecodeError
    ):
        pass

    finally:
        sock.close()

    return None


# ============================================================
# SCAN
# ============================================================

def scan_network(network):
    addresses = list(ipaddress.ip_network(network, strict=False).hosts())

    print(f"Scanning {network}...")
    print(f"Checking {len(addresses)} addresses...")
    print()

    found = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(get_system_config, ip): ip
            for ip in addresses
        }

        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]

            try:
                result = future.result()
            except Exception:
                continue

            if result:
                found.append({
                    "ip": str(ip),
                    **result
                })

    found.sort(
        key=lambda item: ipaddress.ip_address(item["ip"])
    )

    return found


# ============================================================
# DISPLAY
# ============================================================

def display_lights(lights):
    if not lights:
        print("No WiZ lights were found.")
        return

    print("=" * 100)
    print(
        f"{'IP ADDRESS':<16} "
        f"{'ROOM ID':<14} "
        f"{'MAC ADDRESS':<18} "
        f"{'MODEL':<24} "
        f"{'FIRMWARE':<12}"
    )
    print("=" * 100)

    for light in lights:
        print(
            f"{light.get('ip', '-'): <16} "
            f"{str(light.get('roomId', '-')):<14} "
            f"{light.get('mac', '-'): <18} "
            f"{light.get('moduleName', '-'): <24} "
            f"{light.get('fwVersion', '-'): <12}"
        )

    print("=" * 100)
    print()
    print(f"Found {len(lights)} WiZ device(s).")


def display_rooms(lights):
    rooms = {}

    for light in lights:
        room_id = light.get("roomId", "Unknown")

        rooms.setdefault(room_id, []).append(light)

    print()
    print("ROOM SUMMARY")
    print("=" * 60)

    for room_id, room_lights in sorted(
        rooms.items(),
        key=lambda item: str(item[0])
    ):
        print()
        print(f"Room ID: {room_id}")

        for light in room_lights:
            print(
                f"  {light.get('ip', '-')} "
                f"({light.get('moduleName', '-')})"
            )

    print()


# ============================================================
# MAIN
# ============================================================

def main():
    lights = scan_network(NETWORK)

    display_lights(lights)
    display_rooms(lights)


if __name__ == "__main__":
    main()