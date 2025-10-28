"""
ptprint - Production-ready CLI pretty printer and logger

Features:
- Custom logger isolated from other libraries
- Optional Rich integration for pretty CLI output
- Debug mode and info mode
- JSON-only mode for CLI tools
- Bullet types and colorized output
"""

import logging
import os
import re
import shutil
import sys
from typing import Optional, Union

try:
    from rich.logging import RichHandler
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

# ----------------------
# Color and bullet definitions
# ----------------------
COLORS = {
    "TEXT": "\033[0m",
    "INFO": "\033[32m",
    "DEBUG": "\033[34m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "TITLE": "\033[36m",
}

BULLETS = {
    "INFO": "✓",
    "DEBUG": "•",
    "WARNING": "!",
    "ERROR": "✗",
    "TITLE": "#",
    "TEXT": "",
}

# ----------------------
# Logger setup
# ----------------------
logger = logging.getLogger("ptprint")
logger.setLevel(logging.DEBUG)
logger.propagate = False

def setup_logger(
    debug: bool = False,
    logfile: Optional[str] = None,
    json_mode: bool = False,
) -> logging.Logger:
    """
    Configure ptprint logger.

    Args:
        debug: Whether to enable debug-level output to CLI.
        logfile: Optional file path to log all messages.
        json_mode: If True, disables CLI output; only file output or JSON at the end.

    Returns:
        Configured Logger object.
    """
    logger.handlers.clear()
    logger.propagate = False

    if not json_mode:
        if HAVE_RICH and sys.stdout.isatty():
            console_handler = RichHandler(rich_tracebacks=True, show_time=False, show_level=True)
        else:
            console_handler = logging.StreamHandler(sys.stdout)

        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(console_handler)

    if logfile:
        fh = logging.FileHandler(logfile)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

    return logger

# ----------------------
# Helper functions
# ----------------------
def terminal_size() -> tuple[int, int]:
    """Return terminal width and height."""
    size = shutil.get_terminal_size()
    return size.columns, size.lines

def len_without_ansi(text: str) -> int:
    """Return length of string ignoring ANSI escape sequences."""
    ansi_re = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
    return len(ansi_re.sub("", text))

def bullet(bullet_type: Optional[str] = None) -> str:
    """Return colored bullet prefix."""
    if bullet_type and BULLETS.get(bullet_type):
        return f"{COLORS[bullet_type]}[{BULLETS[bullet_type]}]{COLORS['TEXT']} "
    return ""

def color_text(text: str, color: str) -> str:
    """Return text wrapped in ANSI color codes."""
    return f"{COLORS.get(color, COLORS['TEXT'])}{text}{COLORS['TEXT']}"

def clear_line():
    """Clear the current terminal line (posix only)."""
    if os.name == "posix":
        print(" " * terminal_size()[0], end="\r")

# ----------------------
# ptprint API
# ----------------------
def ptprint(
    message: str,
    bullet_type: str = "TEXT",
    condition: Optional[bool] = None,
    end: str = "\n",
    flush: bool = False,
    colortext: Union[bool, str] = False,
    clear_to_eol: bool = False,
    newline_above: bool = False,
    filehandle: Optional[object] = None,
    indent: int = 0
) -> None:
    """
    Pretty print message to CLI and optional filehandle.

    Args:
        message: Message string to print.
        bullet_type: Bullet type key for prefix.
        condition: Only print if True; skip if False.
        end: Line ending character(s).
        flush: Whether to flush stdout.
        colortext: Colorize message; True = bullet color, str = specific color key.
        clear_to_eol: Pad the line with spaces to clear terminal.
        newline_above: Add a newline before message.
        filehandle: Optional file-like object to write message.
        indent: Number of spaces to indent the message.
    """
    if not message:
        return

    bullet_type = bullet_type.upper() if isinstance(bullet_type, str) else ""
    output = message

    if condition is None or condition:
        if colortext:
            if isinstance(colortext, str):
                output = color_text(message, colortext)
            else:
                output = color_text(message, bullet_type)
        else:
            output = f"{bullet(bullet_type)}{message}"
    else:
        return

    if newline_above:
        output = "\n" + output

    if clear_to_eol:
        output += ' ' * (terminal_size()[0] - len_without_ansi(output))

    if indent:
        output = ' ' * indent + output

    print(output, end=end, flush=flush)

    if filehandle:
        clean_text = re.sub(r'\033\[\d+m', '', output)
        filehandle.write(clean_text.lstrip() + end)

# ----------------------
# Convenience logger wrappers
# ----------------------
def debug(msg: str, *args, **kwargs):
    """Log a debug message using ptprint logger."""
    logger.debug(msg, *args, **kwargs)

def info(msg: str, *args, **kwargs):
    """Log an info message using ptprint logger."""
    logger.info(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs):
    """Log a warning message using ptprint logger."""
    logger.warning(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs):
    """Log an error message using ptprint logger."""
    logger.error(msg, *args, **kwargs)

# Shortcut for users who want direct logger access
ptlog = logger
