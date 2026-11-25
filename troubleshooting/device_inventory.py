#!/usr/bin/env python3
# ^ Tells the Mac "run this file with Python 3" — like #! in a shell script.

"""device_inventory.py — Lab Block 1: device identity & health at a glance.

Collects: version, uptime, serial, interface status.
Read-only, enforced by common.safety.
"""
# ^ The docstring: the file's own description. Shows up in tools and
#   tells any engineer (or future you) what this script is for.

# --- IMPORTS: the libraries this script needs -------------------------
# Think of these like loading feature sets on a router: each import
# switches on a capability we use below.

import sys                      # talk to the system: exit with an error, edit the import path
from getpass import getpass     # prompt for a password WITHOUT showing it on screen
from pathlib import Path        # work with file/folder paths cleanly on any OS

import yaml                     # read devices.yaml and turn it into Python data
from netmiko import ConnectHandler   # the SSH "robot typist" that talks to the router

# --- PATH SETUP: make `common/` importable ----------------------------
# __file__ = this script. parents[1] = two levels up = the toolkit root.
# We add the root to Python's search path so `from common.safety import ...`
# works no matter what folder you run the script from. (Portability rule.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.safety import safe_send   # the read-only guard — mandatory in every script



def load_device(name: str) -> dict:
    """Read one device's connection info from devices.yaml."""
    # Find devices.yaml in the toolkit root (same trick as the path setup above).
    toolkit_root = Path(__file__).resolve().parents[1]

    # Open the file and let yaml turn the text into a dictionary:
    # {"sandbox-cat8k": {"device_type": "cisco_xe", "host": "...", ...}}
    with open(toolkit_root / "devices.yaml") as f:
        all_devices = yaml.safe_load(f)

    # If the name isn't in the file, stop right here with a clear message
    # instead of failing mysteriously later.
    if name not in all_devices:
        sys.exit(f"Device '{name}' not found in devices.yaml")

    # Hand back just that one device's connection info.
    return all_devices[name]

def check_version(conn) -> bool:
    """Check 1: device responds and reports its version/serial/uptime."""
    # Ask the router for its identity. safe_send = send_command + whitelist guard.
    output = safe_send(conn, "show version")

    # Start with "?" placeholders — if parsing finds nothing, we'll know.
    version = serial = uptime = "?"

    # Walk the output line by line, same as your eyes would on a terminal,
    # and grab the three facts we care about.
    for line in output.splitlines():
        if "Cisco IOS XE Software, Version" in line:
            # Line looks like: "Cisco IOS XE Software, Version 17.12.02"
            # split on "Version", take what's after it, trim the spaces.
            version = line.split("Version")[-1].strip()
        elif "Processor board ID" in line:
            # Line looks like: "Processor board ID 9Z9OXRWZ50D"
            # split into words, the serial is the last word.
            serial = line.split()[-1]
        elif " uptime is " in line:
            # Line looks like: "cat8000v uptime is 2 hours, 11 minutes"
            # everything after " uptime is " = the uptime.
            uptime = line.split(" uptime is ")[-1]

    # PASS only if we actually found a version (device answered sensibly).
    ok = version != "?"
    print(f"[{'PASS' if ok else 'FAIL'}] Version check — IOS XE {version}, serial {serial}, up {uptime}")
    return ok


def check_interfaces(conn) -> bool:
    """Check 2: list interfaces; FAIL if any are up/down (likely L1/L2 problem)."""
    # One command, same as you'd type it: show ip int brief.
    output = safe_send(conn, "show ip interface brief")

    # We'll collect names of any interface in the bad up/down state here.
    problems = []

    for line in output.splitlines():
        parts = line.split()          # chop the line into words
        # Real data rows have 6+ columns; skip the "Interface ..." header row.
        if len(parts) >= 6 and parts[0] != "Interface":
            # Column layout: name is first, protocol is last, status next-to-last.
            name, status, protocol = parts[0], parts[-2], parts[-1]
            print(f"       {name:<30} status={status:<18} protocol={protocol}")

            # up/down = cable in, line protocol dead — THE classic L2 fault.
            # (down/down just means nothing's plugged in — not a fault.)
            if status == "up" and protocol == "down":
                problems.append(name)

    # PASS means the problems list stayed empty.
    ok = not problems
    print(f"[{'PASS' if ok else 'FAIL'}] Interface check — {len(problems)} interface(s) up/down: {', '.join(problems) or 'none'}")

    # Ground Rule 4: on FAIL, print a read-only NOTE — the next command YOU
    # would type to dig in. The script suggests; Nelson types.
    if problems:
        print(f"       NOTE: review L2 on {problems[0]} — suggested look: show interface {problems[0]}")

    return ok


def main():
    # Step 1: pull the connection info for this device from devices.yaml.
    # (Same as opening your SecureCRT saved session — host, user, type.)
    device = load_device("sandbox-cat8k")

    # Step 2: ask for the password now, at runtime — it lives nowhere on disk.
    device["password"] = getpass("Device password: ")

    print(f"\n=== Device Inventory: {device['host']} ===\n")

    # Step 3: open the SSH session. "with" = auto-logout when the block ends,
    # even if something crashes mid-run. No orphaned vty lines.
    with ConnectHandler(**device) as conn:
        # Step 4: run the checks IN ORDER — the methodology. Each returns
        # True (PASS) or False (FAIL), and we keep the list of results.
        results = [
            check_version(conn),
            check_interfaces(conn),
        ]

    # Step 5: the scoreboard. True counts as 1, so sum = number of PASSes.
    passed = sum(results)
    print(f"\n=== {passed}/{len(results)} checks passed ===")


# Only call main() when this file is run directly (python device_inventory.py),
# not when another script imports something from it.
if __name__ == "__main__":
    main()