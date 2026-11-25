#!/usr/bin/env python3
"""device_inventory.py — Lab Block 1: device identity & health at a glance.

Collects: version, uptime, serial, interface status.
Read-only, enforced by common.safety.
"""

import sys
from getpass import getpass
from pathlib import Path

import yaml
from netmiko import ConnectHandler

# Make the toolkit root importable no matter where we run from
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.safety import safe_send


def load_device(name: str) -> dict:
    """Read one device's connection info from devices.yaml."""
    toolkit_root = Path(__file__).resolve().parents[1]
    with open(toolkit_root / "devices.yaml") as f:
        all_devices = yaml.safe_load(f)

    if name not in all_devices:
        sys.exit(f"Device '{name}' not found in devices.yaml")

    return all_devices[name]

def check_version(conn) -> bool:
    """Check 1: device responds and reports its version/serial/uptime."""
    output = safe_send(conn, "show version")

    version = serial = uptime = "?"
    for line in output.splitlines():
        if "Cisco IOS XE Software, Version" in line:
            version = line.split("Version")[-1].strip()
        elif "Processor board ID" in line:
            serial = line.split()[-1]
        elif " uptime is " in line:
            uptime = line.split(" uptime is ")[-1]

    ok = version != "?"
    print(f"[{'PASS' if ok else 'FAIL'}] Version check — IOS XE {version}, serial {serial}, up {uptime}")
    return ok


def check_interfaces(conn) -> bool:
    """Check 2: list interfaces; FAIL if any are up/down (likely L1/L2 problem)."""
    output = safe_send(conn, "show ip interface brief")
    problems = []

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0] != "Interface":
            name, status, protocol = parts[0], parts[-2], parts[-1]
            print(f"       {name:<30} status={status:<18} protocol={protocol}")
            if status == "up" and protocol == "down":
                problems.append(name)

    ok = not problems
    print(f"[{'PASS' if ok else 'FAIL'}] Interface check — {len(problems)} interface(s) up/down: {', '.join(problems) or 'none'}")

    if problems:
        print(f"       NOTE: review L2 on {problems[0]} — suggested look: show interface {problems[0]}")

    return ok


def main():
    device = load_device("sandbox-cat8k")
    device["password"] = getpass("Device password: ")

    print(f"\n=== Device Inventory: {device['host']} ===\n")

    with ConnectHandler(**device) as conn:
        results = [
            check_version(conn),
            check_interfaces(conn),
        ]

    passed = sum(results)
    print(f"\n=== {passed}/{len(results)} checks passed ===")


if __name__ == "__main__":
    main()
