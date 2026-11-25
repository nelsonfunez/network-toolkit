# Network Toolkit

Read-only network troubleshooting and discovery scripts (Python + Netmiko).
Built lab-by-lab on the road from CCNA refresh to CCNP Enterprise (ENCOR).

## Principles

- **100% read-only** — scripts send `show` commands only, never config mode. Enforced in code.
- **Methodology-driven** — each script walks troubleshooting checks in proper order, printing PASS/FAIL per step.
- **Fix suggestions, not fixes** — on a FAIL, the script prints the suggested fix command with real values from the device, for the engineer to review and type manually.
- **Portable** — runs from any machine with SSH access to the device (lab or production, with permission).

## Structure

- `/troubleshooting` — one script per topic (VLANs, OSPF, STP, ...)
- `/discovery` — new-device discovery and baseline recommendation
- `/labs` — lab topologies and break/fix scenario configs

## Tested against

- Cisco DevNet Sandbox (Catalyst 8000v, IOS XE)
- Cisco Modeling Labs (CML Free)
