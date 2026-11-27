#!/usr/bin/env python3
"""
vlan_check.py — Access-port / port-security troubleshooter (READ-ONLY)

Lab Block 2 deliverable. Built for the real-world ticket Nelson sees daily:
"a user's port is dead" — usually a port-security violation that err-disabled
the interface.

Hand it a switch and an interface; it walks the checks in troubleshooting
order and prints PASS/FAIL per step, then — if it finds the port shut by a
violation — prints a NOTE with the exact recovery commands, pre-filled with
the real values read off the device, for YOU to review and type by hand.

    python troubleshooting/vlan_check.py <device-name> <interface>
    e.g.  python troubleshooting/vlan_check.py cml-sw1 Ethernet0/1

READ-ONLY: every device command goes through common/safety.py (show-only
whitelist). This script never configures anything.
"""

# ---------------------------------------------------------------------------
# Imports — same toolset as device_inventory.py, so nothing new to learn here.
# ---------------------------------------------------------------------------
import sys                      # read the command-line arguments the user typed
from getpass import getpass     # prompt for the password WITHOUT echoing it
from pathlib import Path        # build file paths that work on any OS

import yaml                     # read devices.yaml into a Python dict
from netmiko import ConnectHandler   # the SSH "robot typist" that drives the switch

# Make the toolkit root importable so "from common..." works no matter where
# you run the script from — same trick device_inventory.py uses.
# (venv = VRF for Python; this is adding a route so the import resolves.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.safety import safe_send   # the read-only guard — mandatory everywhere


# ---------------------------------------------------------------------------
# COMMAND_LOG — a running list of every show command the script sends.
# We collect them so we can print a "run these yourself" cheat-sheet at the
# end: the exact commands a human would use to troubleshoot this same port by
# hand. It's a plain module-level list; run_show() below appends to it.
# ---------------------------------------------------------------------------
COMMAND_LOG: list[str] = []


def run_show(conn, command: str) -> str:
    """Send a show command through the read-only guard AND log it.

    Thin wrapper around safe_send: same safety (show/ping/traceroute only),
    but it also records the command in COMMAND_LOG so main() can print the
    full list of relevant troubleshooting commands at the end.
    """
    COMMAND_LOG.append(command)
    return safe_send(conn, command)


# ---------------------------------------------------------------------------
# load_device() — identical pattern to device_inventory.py.
# Pull one device's connection info out of devices.yaml by name.
# ---------------------------------------------------------------------------
def load_device(name: str) -> dict:
    """Read one device's connection info from devices.yaml."""
    toolkit_root = Path(__file__).resolve().parents[1]
    with open(toolkit_root / "devices.yaml") as f:
        all_devices = yaml.safe_load(f)

    if name not in all_devices:
        # Fail loud and clear instead of a confusing crash later.
        print(f"[ERROR] '{name}' not found in devices.yaml")
        sys.exit(1)

    return all_devices[name]


# ---------------------------------------------------------------------------
# normalize_interface() — small helper so the user can be lazy about typing.
# IOS accepts "Et0/1", "Eth0/1", "Ethernet0/1" — we expand short forms to the
# full name the "show" commands expect. Like how IOS lets you type "int e0/1".
# ---------------------------------------------------------------------------
def normalize_interface(intf: str) -> str:
    """Turn 'Et0/1', 'eth0/1', or 'Ethernet0/1' into 'Ethernet0/1'.

    How it works: strip the letters off the front, keep the number part
    (e.g. '0/1'), and glue the full word 'Ethernet' back on. Checking the
    longest prefixes first ('ethernet' before 'eth' before 'et') matters —
    otherwise 'et' would match 'ethernet0/1' and leave 'hernet0/1' behind.
    """
    low = intf.lower()
    for prefix in ("ethernet", "eth", "et"):
        if low.startswith(prefix):
            number_part = intf[len(prefix):]   # everything after the letters, e.g. '0/1'
            return "Ethernet" + number_part
    # Not an Ethernet name we recognize — leave it exactly as the user typed it.
    return intf


# ===========================================================================
# CHECK 1 — Interface status: is it UP, or err-disabled by a violation?
# This is the money check for the daily ticket. We look at:
#   show interfaces <intf> status
# and flag err-disable immediately.
# ===========================================================================
def check_interface_status(conn, intf: str) -> tuple[bool, str]:
    """
    Returns (ok, status_word).
    ok  = True  when the port is 'connected'/up.
    ok  = False when it's err-disabled, notconnect, or disabled.
    status_word is the raw status we found (used by later checks/notes).
    """
    # "show interfaces Ethernet0/1 status" prints a one-row table:
    #   Port   Name   Status       Vlan   Duplex  Speed Type
    #   Et0/1         err-disabled 10     auto    auto  ...
    output = run_show(conn, f"show interfaces {intf} status")

    status_word = "?"
    for line in output.splitlines():
        # The data row starts with the short port name (Et0/1). Skip the
        # header line ("Port ...") and any blank lines.
        if line.strip().startswith("Et"):
            parts = line.split()
            # parts = ['Et0/1', 'err-disabled', '10', ...]  (no Name set)
            #   or   ['Et0/1', 'SomeName', 'connected', '10', ...] (Name set)
            # The status is whichever field equals a known status keyword.
            for p in parts:
                if p in ("connected", "err-disabled", "notconnect", "disabled"):
                    status_word = p
                    break
            break

    ok = (status_word == "connected")
    return ok, status_word


# ===========================================================================
# CHECK 2 — Access VLAN: which VLAN is the port in, and does that VLAN exist
# and is it active? A port assigned to a missing/suspended VLAN is a classic
# "it's configured but still doesn't work" fault.
# ===========================================================================
def check_access_vlan(conn, intf: str) -> tuple[bool, str]:
    """
    Returns (ok, vlan_id).
    Reads the port's access VLAN from 'show interfaces <intf> switchport',
    then confirms that VLAN is active in 'show vlan brief'.
    """
    sw = run_show(conn, f"show interfaces {intf} switchport")

    access_vlan = "?"
    for line in sw.splitlines():
        # Line looks like: "Access Mode VLAN: 10 (USERS)"
        if "Access Mode VLAN:" in line:
            # take the piece after the colon, then the first token = the number
            access_vlan = line.split("Access Mode VLAN:")[-1].strip().split()[0]
            break

    # If we couldn't find an access VLAN, the port may be a trunk or
    # mis-set — report that rather than pretending it's fine.
    if access_vlan in ("?", "none"):
        return False, access_vlan

    # Now confirm that VLAN exists AND is active in the VLAN database.
    vlans = run_show(conn, "show vlan brief")
    vlan_active = False
    for line in vlans.splitlines():
        parts = line.split()
        # Row looks like: "10   USERS   active   Et0/1, Et0/2"
        if parts and parts[0] == access_vlan:
            vlan_active = ("active" in line)
            break

    return vlan_active, access_vlan


# ===========================================================================
# CHECK 3 — Port-security enabled & its posture (mode, max MACs).
# Reads 'show port-security interface <intf>'. We don't fail just because
# port-security is on — we report the posture so the next check can judge.
# ===========================================================================
def check_port_security_config(conn, intf: str) -> tuple[bool, dict]:
    """
    Returns (enabled, facts) where facts is a dict with the fields we parsed:
    port_status, violation_mode, max_mac, total_mac, violation_count,
    last_source.
    """
    ps = run_show(conn, f"show port-security interface {intf}")

    facts = {
        "port_status": "?",
        "violation_mode": "?",
        "max_mac": "?",
        "total_mac": "?",
        "violation_count": "?",
        "last_source": "?",
    }
    enabled = False

    for line in ps.splitlines():
        s = line.strip()
        # Each fact is "Label : value" — split once on the colon.
        if s.startswith("Port Security") and ":" in s:
            enabled = ("Enabled" in s)
        elif s.startswith("Port Status"):
            facts["port_status"] = s.split(":", 1)[1].strip()
        elif s.startswith("Violation Mode"):
            facts["violation_mode"] = s.split(":", 1)[1].strip()
        elif s.startswith("Maximum MAC Addresses"):
            facts["max_mac"] = s.split(":", 1)[1].strip()
        elif s.startswith("Total MAC Addresses"):
            facts["total_mac"] = s.split(":", 1)[1].strip()
        elif s.startswith("Security Violation Count"):
            facts["violation_count"] = s.split(":", 1)[1].strip()
        elif s.startswith("Last Source Address"):
            # "Last Source Address:Vlan : 5254.00de.ad01:10"
             # Grab the value side after the last ": ", giving "5254.00de.ad02:10",
            # then drop the trailing ":<vlan>" with rsplit to leave just the MAC.
            value = s.rsplit(": ", 1)[-1].strip()
            facts["last_source"] = value.rsplit(":", 1)[0]          
            

    return enabled, facts


# ===========================================================================
# CHECK 4 — Violation check: has a violation actually fired?
# We judge from the facts we already read: a non-zero violation count, or a
# Secure-shutdown status, means the port tripped.
# ===========================================================================
def check_violation(facts: dict) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok = True  when there's no violation (count 0, status Secure-up).
    ok = False when a violation has fired.
    """
    count = facts.get("violation_count", "0")
    status = facts.get("port_status", "")

    # Secure-shutdown is the tell-tale: the port security feature shut it.
    if status == "Secure-shutdown":
        return False, f"port is Secure-shutdown; offending MAC {facts.get('last_source')}"

    # A non-zero violation counter also means something tripped.
    if count.isdigit() and int(count) > 0:
        return False, f"violation count = {count}; offending MAC {facts.get('last_source')}"

    return True, "no violations"


# ---------------------------------------------------------------------------
# print_recovery_note() — the READ-ONLY fix suggestion.
# We NEVER configure. When the port is err-disabled by a violation, we print
# the exact commands YOU would type to recover it, pre-filled with the real
# interface name. (Ground Rule 4: suggest, never execute.)
# ---------------------------------------------------------------------------
def print_recovery_note(intf: str, facts: dict) -> None:
    print()
    print("  " + "-" * 66)
    print("  NOTE — suggested recovery (READ-ONLY script; type these yourself):")
    print("  " + "-" * 66)
    print(f"  The offending device MAC was: {facts.get('last_source', '?')}")
    print("  1) Find/confirm the rogue device is gone, then bounce the port:")
    print(f"       configure terminal")
    print(f"       interface {intf}")
    print(f"       shutdown")
    print(f"       no shutdown")
    print(f"       end")
    print("  2) If the legit device's MAC changed on purpose, clear the old")
    print("     sticky entry first, then let it re-learn:")
    print(f"       configure terminal")
    print(f"       interface {intf}")
    print(f"       no switchport port-security mac-address sticky")
    print(f"       switchport port-security mac-address sticky")
    print(f"       end")
    print("  (Optional) Auto-recover err-disable in future, globally:")
    print("       errdisable recovery cause psecure-violation")
    print("  " + "-" * 66)


# ===========================================================================
# main() — wire it all together, print the PASS/FAIL scoreboard.
# ===========================================================================
def main():
    # --- Read the two command-line arguments: device name + interface. ---
    # sys.argv[0] is the script name; [1] device, [2] interface.
    if len(sys.argv) < 3:
        print("Usage: python vlan_check.py <device-name> <interface>")
        print("  e.g. python vlan_check.py cml-sw1 Ethernet0/1")
        sys.exit(1)

    device_name = sys.argv[1]
    intf = normalize_interface(sys.argv[2])

    # --- Load connection info and prompt for the password at runtime. ---
    device = load_device(device_name)
    device["password"] = getpass("Device password: ")

    print(f"\n=== VLAN / Port-Security Check: {device_name} {intf} ===\n")

    # --- Connect once; all checks reuse the same SSH session. ---
    # "with" auto-closes the connection when we're done (even on error).
    results = []  # collect (ok, label) for the final tally
    with ConnectHandler(**device) as conn:

        # CHECK 1 — interface status / err-disable
        ok1, status = check_interface_status(conn, intf)
        results.append(ok1)
        verdict = "PASS" if ok1 else "FAIL"
        print(f"[{verdict}] Interface status — {intf} is '{status}'")

        # CHECK 2 — access VLAN exists & active
        ok2, vlan = check_access_vlan(conn, intf)
        results.append(ok2)
        verdict = "PASS" if ok2 else "FAIL"
        print(f"[{verdict}] Access VLAN — port in VLAN {vlan}, active in DB: {ok2}")

        # CHECK 3 — port-security posture (informational; always 'read')
        enabled, facts = check_port_security_config(conn, intf)
        print(f"[INFO] Port-security — enabled: {enabled}, "
              f"status: {facts['port_status']}, mode: {facts['violation_mode']}, "
              f"max: {facts['max_mac']}, current: {facts['total_mac']}")

        # CHECK 4 — did a violation fire?
        ok4, reason = check_violation(facts)
        results.append(ok4)
        verdict = "PASS" if ok4 else "FAIL"
        print(f"[{verdict}] Violation check — {reason}")

        # If the port is err-disabled by a violation, print the recovery note.
        if status == "err-disabled" or not ok4:
            print_recovery_note(intf, facts)

    # --- Final scoreboard: how many of the 3 pass/fail checks passed. ---
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===")

    # --- Relevant-commands cheat-sheet -------------------------------------
    # Print every show command the script used, so you can re-run them by hand
    # to dig deeper — ready to copy into a ticket. We also add a few extra
    # read-only commands that are handy for this ticket type but that the
    # script doesn't parse itself (log history, err-disable recovery state).
    print("\n--- Relevant commands to run manually (all READ-ONLY) ---")
    # The ones the script actually ran (deduplicated, in order):
    seen = set()
    for cmd in COMMAND_LOG:
        if cmd not in seen:
            seen.add(cmd)
            print(f"  {cmd}")
    # Extra commands worth a human's eyes on a port-security ticket:
    print("  show port-security address        ! all secured MACs, system-wide")
    print("  show errdisable recovery          ! is auto-recovery on? timer?")
    print(f"  show logging | include {intf}   ! this port's log history")
    print("---------------------------------------------------------")


if __name__ == "__main__":
    main()
