"""safety.py — read-only guard for all toolkit scripts.

Every script sends its commands through safe_send(). If a command
doesn't start with an approved read-only keyword, it is refused.
"""

# The ONLY command types this toolkit is allowed to send.
# Everything else — configure, reload, write, clear — gets rejected.
ALLOWED_COMMANDS = ("show", "ping", "traceroute")


class CommandNotAllowed(Exception):
    """Raised when a script tries to send a non-read-only command."""


def check_command(command: str) -> str:
    """Verify a command is read-only. Returns it clean, or raises."""
    clean = command.strip().lower()

    if not clean.startswith(ALLOWED_COMMANDS):
        raise CommandNotAllowed(
            f"BLOCKED: '{command}' — this toolkit is read-only. "
            f"Allowed commands start with: {', '.join(ALLOWED_COMMANDS)}"
        )

    return command.strip()


def safe_send(conn, command: str, **kwargs) -> str:
    """Send a read-only command through an open Netmiko connection.

    Drop-in replacement for conn.send_command() — but guarded.
    """
    return conn.send_command(check_command(command), **kwargs)