import sqlite3
import json
import os
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from emulator.db import _get_db_path

log = logging.getLogger("emulator.end_experiment")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


def end_experiment(experiment: str) -> None:
    """Replicate the 'End experiment' button: unassign workers, stop jobs, log event."""

    db_path = _get_db_path()

    # 1. Query currently assigned workers
    assigned_workers = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT pioreactor_unit FROM experiment_worker_assignments WHERE experiment = ?",
                (experiment,),
            ).fetchall()
            conn.close()
            assigned_workers = [r[0] for r in rows] if rows else []
        except Exception as e:
            log.warning(f"Failed to query worker assignments: {e}")

    # 2. Delete assignments from DB (trigger auto-sets unassigned_at in history)
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "DELETE FROM experiment_worker_assignments WHERE experiment = ?",
                (experiment,),
            )
            conn.commit()
            conn.close()
            log.info(f"Deleted worker assignments for experiment '{experiment}'")
        except Exception as e:
            log.warning(f"Failed to delete worker assignments: {e}")

    # 3. Publish MQTT unassignment + stop jobs + log event
    try:
        client = mqtt.Client(
            client_id=f"emulator_end_{os.getpid()}", protocol=mqtt.MQTTv311
        )
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        for unit in assigned_workers:
            # Unassign worker (retained)
            assignment_payload = json.dumps({
                "pioreactor_unit": unit,
                "experiment": None,
                "assigned_at": None,
                "updated_at": now,
            })
            client.publish(
                f"pioreactor/{unit}/$experiment/assignment",
                assignment_payload,
                qos=1,
                retain=True,
            )

            # Note: stopping jobs via MQTT wildcards is not possible (wildcards
            # only work in subscribe topics). The DB unassignment above is
            # sufficient — the backend's jobs will detect the cleared assignment
            # and exit naturally.

            # Publish log entry
            log_payload = json.dumps({
                "message": f"Removed all workers from {experiment}.",
                "task": "assignment",
                "source": "emulator",
                "level": "INFO",
                "timestamp": now,
            })
            client.publish(
                f"pioreactor/{unit}/{experiment}/logs/emulator/info",
                log_payload,
                qos=1,
            )

        client.loop_stop()
        client.disconnect()

        log.info(
            f"Published unassignment + stop for {len(assigned_workers)} worker(s): "
            + ", ".join(assigned_workers)
        )
    except Exception as e:
        log.warning(f"Failed to publish MQTT end-experiment messages: {e}")

    log.info(f"Experiment '{experiment}' ended")
