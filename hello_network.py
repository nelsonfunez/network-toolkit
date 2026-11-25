#!/usr/bin/env python3
"""hello_network.py — first script: SSH to a router, run 'show version', print it."""

from getpass import getpass
from netmiko import ConnectHandler

device = {
    "device_type": "cisco_xe",
    "host": "10.10.20.48",
    "username": "developer",
    "password": getpass("Device password: "),
}

print(f"Connecting to {device['host']} ...")

with ConnectHandler(**device) as conn:
    output = conn.send_command("show version")

print(output)
print("\n--- That output traveled over SSH from a real router. ---")
