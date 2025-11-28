#!/usr/bin/env python3
"""
HomeKit Device Discovery Tool
==============================

Discovers HomeKit devices on your network and generates sensor configuration
for homekit_logger.py.

Requirements:
    pip install aiohomekit

Note: This requires that your HomeKit devices are accessible via HAP (HomeKit
Accessory Protocol). Some devices may only be accessible through their hub.

Alternative: Use the iOS Shortcuts app to list your HomeKit devices:
1. Create a new Shortcut
2. Add "Get State of Home"
3. Run it to see all available devices and their properties
"""

import argparse
import asyncio
import sys

try:
    from aiohomekit.controller import Controller

    AIOHOMEKIT_AVAILABLE = True
except ImportError:
    AIOHOMEKIT_AVAILABLE = False


def generate_field_name(room: str, sensor_type: str) -> str:
    """Generate a valid field name from room and sensor type."""
    # Convert to lowercase, replace spaces with underscores
    room_clean = room.lower().replace(" ", "_").replace("-", "_")
    # Remove any non-alphanumeric characters except underscores
    room_clean = "".join(c for c in room_clean if c.isalnum() or c == "_")
    return f"{room_clean}_{sensor_type}"


def print_sensor_config(devices: list[dict]) -> None:
    """Print Python code for SENSORS configuration."""
    print("\n# Add these to your SENSORS list in homekit_logger.py:")
    print("SENSORS = [")

    for device in devices:
        room = device.get("room", "unknown")
        print(f"    # {room}")

        if device.get("has_temperature"):
            field = generate_field_name(room, "temp")
            print(
                f'    {{"field": "{field}", "name": "{room} Temperature", "unit": "°C"}},'
            )

        if device.get("has_humidity"):
            field = generate_field_name(room, "humidity")
            print(
                f'    {{"field": "{field}", "name": "{room} Humidity", "unit": "%"}},'
            )

        if device.get("has_co2"):
            field = generate_field_name(room, "co2")
            print(f'    {{"field": "{field}", "name": "{room} CO2", "unit": "ppm"}},')

        if device.get("has_air_quality"):
            field = generate_field_name(room, "air_quality")
            print(
                f'    {{"field": "{field}", "name": "{room} Air Quality", "unit": ""}},'
            )

    print("]")


async def discover_devices() -> list[dict]:
    """Discover HomeKit devices on the network."""
    if not AIOHOMEKIT_AVAILABLE:
        print("aiohomekit not installed. Install with: pip install aiohomekit")
        return []

    controller = Controller()
    devices = []

    print("Discovering HomeKit devices (this may take 30 seconds)...")

    try:
        discoveries = await controller.discover_ip(timeout=30)

        for discovery in discoveries:
            device_info = {
                "name": discovery.description.name,
                "model": discovery.description.model,
                "room": discovery.description.name,  # Default to device name
                "has_temperature": False,
                "has_humidity": False,
                "has_co2": False,
                "has_air_quality": False,
            }

            # Check characteristic types if we can pair
            # Note: Full pairing requires setup code
            print(
                f"Found: {discovery.description.name} ({discovery.description.model})"
            )

            devices.append(device_info)

    except Exception as e:
        print(f"Discovery error: {e}")

    return devices


def manual_entry() -> list[dict]:
    """Interactive manual entry of devices."""
    devices = []
    print("\nManual Device Entry")
    print("=" * 40)
    print("Enter your HomeKit rooms/devices. Type 'done' when finished.\n")

    while True:
        room = input("Room name (or 'done'): ").strip()
        if room.lower() == "done":
            break
        if not room:
            continue

        device = {"room": room}

        has_temp = input(f"  Does {room} have temperature sensor? (y/n): ").lower()
        device["has_temperature"] = has_temp in ("y", "yes")

        has_humidity = input(f"  Does {room} have humidity sensor? (y/n): ").lower()
        device["has_humidity"] = has_humidity in ("y", "yes")

        has_co2 = input(f"  Does {room} have CO2 sensor? (y/n): ").lower()
        device["has_co2"] = has_co2 in ("y", "yes")

        devices.append(device)
        print()

    return devices


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover HomeKit devices and generate sensor configuration"
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Manually enter devices instead of auto-discovery",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Attempt automatic discovery (requires aiohomekit)",
    )
    args = parser.parse_args()

    if args.discover:
        if not AIOHOMEKIT_AVAILABLE:
            print("Error: aiohomekit not installed")
            print("Install with: pip install aiohomekit")
            print("\nAlternatively, use --manual for interactive entry")
            sys.exit(1)

        devices = asyncio.run(discover_devices())
        if devices:
            print_sensor_config(devices)
        else:
            print("\nNo devices found. Try --manual mode instead.")

    elif args.manual:
        devices = manual_entry()
        if devices:
            print_sensor_config(devices)

    else:
        print("HomeKit Device Discovery Tool")
        print("=" * 40)
        print("\nOptions:")
        print("  --manual    Manually enter your rooms/devices")
        print("  --discover  Auto-discover devices (requires: pip install aiohomekit)")
        print("\nExample:")
        print("  python discover_homekit.py --manual")
        print("\nAlternative: Use iOS Shortcuts to list devices:")
        print("  1. Create Shortcut with 'Get State of Home' action")
        print("  2. View output to see all devices and their sensors")


if __name__ == "__main__":
    main()
