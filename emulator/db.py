import sqlite3
import json
import os
import logging
from datetime import datetime

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
