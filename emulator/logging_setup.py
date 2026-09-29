import os
import re
import glob
import logging
import logging.handlers
from datetime import datetime, timedelta, timezone

STATE_DIR = os.environ.get("STATE_DIR", "/app/state")
LOG_FILE = os.path.join(STATE_DIR, "emulator.log")

MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

LOG_TIMEZONE = os.environ.get("EMULATOR_LOG_TZ", "UTC-3")


def parse_timezone(name):
    """Turn 'UTC-3', 'UTC+05:30', '-3' or '3' into a fixed-offset tzinfo.

    Falls back to UTC when the value cannot be parsed.
    """
    text = str(name).strip().upper()
    if text in ("UTC", "Z", ""):
        return timezone.utc
    match = re.fullmatch(r"(?:UTC|GMT)?\s*([+-]?)(\d{1,2})(?::?(\d{2}))?", text)
    if not match:
        raise ValueError(f"invalid timezone: {name!r} (expected e.g. 'UTC-3')")
    sign = -1 if match.group(1) == "-" else 1
    hours = int(match.group(2))
    minutes = int(match.group(3) or 0)
    if hours > 14 or minutes > 59:
        raise ValueError(f"timezone out of range: {name!r}")
    offset = sign * timedelta(hours=hours, minutes=minutes)
    return timezone(timedelta(0) if offset == timedelta(0) else offset, name.strip())


LOG_TZ = parse_timezone(LOG_TIMEZONE)


class TZFormatter(logging.Formatter):
    """Formatter that renders asctime as ISO-8601 in LOG_TZ."""

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, LOG_TZ).isoformat(
            timespec="seconds"
        )


def setup_logging(level=logging.INFO):
    if logging.getLogger().handlers:
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                LOG_FILE,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            ),
        ],
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(TZFormatter(LOG_FORMAT, LOG_DATEFMT))


def reset_log_file():
    """Detach the file handler and delete the log file plus its rotations."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()

    removed = []
    for path in sorted(glob.glob(LOG_FILE + "*")):
        os.remove(path)
        removed.append(os.path.basename(path))
    return removed
