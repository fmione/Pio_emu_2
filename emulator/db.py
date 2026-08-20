import sqlite3
import json
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger("emulator.db")


def _get_db_path():
    return os.environ.get("PIO_DB_PATH", "/home/pioreactor/.pioreactor/storage/pioreactor.sqlite")


def _get_config():
    config_path = os.environ.get("CONFIG_PATH", "/app/model/EMULATOR_config.json")
    with open(config_path) as f:
        return json.load(f)


def clean_db():
    config = _get_config()
    exp_name = config["exp_name"]
    db_path = _get_db_path()

    if not os.path.exists(db_path):
        log.warning(f"Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM experiments WHERE experiment = ?", (exp_name,))
    conn.commit()
    conn.close()
    log.info(f"Cleaned experiment '{exp_name}' from database")


def init_db():
    config = _get_config()
    exp_name = config["exp_name"]
    mbr_list = config["Brxtor_list"]
    db_path = _get_db_path()

    start_datetime = datetime.now().replace(microsecond=0).isoformat()

    if not os.path.exists(db_path):
        log.warning(f"Database not found: {db_path}")
        return start_datetime

    conn = sqlite3.connect(db_path)

    for unit in mbr_list:
        conn.execute(
            "INSERT OR IGNORE INTO workers (pioreactor_unit, added_at, is_active) VALUES (?, ?, 1)",
            (unit, start_datetime),
        )

    conn.execute(
        "INSERT OR IGNORE INTO experiments (experiment, created_at) VALUES (?, ?)",
        (exp_name, start_datetime),
    )

    for unit in mbr_list:
        conn.execute(
            "INSERT OR IGNORE INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) VALUES (?, ?, ?)",
            (unit, exp_name, start_datetime),
        )

    conn.commit()
    conn.close()
    log.info(f"Initialized experiment '{exp_name}' with workers {mbr_list}")

    return start_datetime


def get_dosing_events(start_datetime):
    """
    Read add_media dosing events from Pioreactor DB and return feed profiles
    grouped by bioreactor unit, compatible with EMULATOR_design.json format.

    Returns:
        dict: {unit: {"time_feed": [...], "Feed_profile": [...]}} or empty dict on error.
    """
    config = _get_config()
    exp_name = config["exp_name"]
    mbr_list = config["Brxtor_list"]
    db_path = _get_db_path()

    if not os.path.exists(db_path):
        log.warning(f"Database not found: {db_path}")
        return {}

    # Parse start_datetime as UTC
    start_time = datetime.fromisoformat(start_datetime)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT timestamp, volume_change_ml, pioreactor_unit "
            "FROM dosing_events "
            "WHERE experiment = ? AND pioreactor_unit IN ({}) AND event = 'add_media' "
            "ORDER BY timestamp".format(", ".join("?" * len(mbr_list))),
            (exp_name, *mbr_list),
        ).fetchall()
        conn.close()
    except Exception as e:
        log.warning(f"Failed to read dosing events: {e}")
        return {}

    if not rows:
        return {}

    # Parse timestamps and convert to relative hours
    events = []
    for ts_str, volume, unit in rows:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hours = (ts - start_time).total_seconds() / 3600
        if hours >= 0:
            events.append((unit, round(hours, 4), volume))

    if not events:
        return {}

    # Group by unit
    result = {}
    for unit in mbr_list:
        unit_events = sorted([(h, v) for u, h, v in events if u == unit])
        if not unit_events:
            continue

        # Aggregate pulses within 2-minute window
        time_window = 2 / 60
        groups = []
        current_group = [unit_events[0]]

        for prev, curr in zip(unit_events, unit_events[1:]):
            if curr[0] - current_group[-1][0] > time_window:
                groups.append(current_group)
                current_group = [curr]
            else:
                current_group.append(curr)
        groups.append(current_group)

        time_feed = [round(g[0][0], 4) for g in groups]
        feed_profile = [round(sum(v for _, v in g), 4) for g in groups]
        result[unit] = {"time_feed": time_feed, "Feed_profile": feed_profile}

    parts = [f"{u}={len(d['time_feed'])} pulses" for u, d in result.items()]
    log.info(f"Loaded dosing events: {', '.join(parts)}")
    return result
