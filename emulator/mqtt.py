import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
STATE_DIR = os.environ.get("STATE_DIR", "/app/state")
MODEL_DIR = os.environ.get("MODEL_DIR", "/app/model")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("emulator.mqtt")


# ---------------------------------------------------------------------------
# State persistence (last_published.json)
# ---------------------------------------------------------------------------

def _last_published_path():
    return os.path.join(STATE_DIR, "last_published.json")


def _load_last_published():
    path = _last_published_path()
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_last_published(data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_last_published_path(), "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def measurement_time_to_datetime(start_datetime: datetime, mt_hours: float) -> datetime:
    return start_datetime + timedelta(hours=mt_hours)


def find_new_entries(prev_times, curr_times, curr_values):
    prev_set = set(prev_times)
    return [(t, v) for t, v in zip(curr_times, curr_values) if t not in prev_set]


# ---------------------------------------------------------------------------
# Measurement handlers
# ---------------------------------------------------------------------------

def publish_od_reading(client, unit, experiment, data, start_datetime, is_first):
    """Publish OD readings to pioreactor/{unit}/{exp}/od_reading/od2."""
    curr_times = data.get("measurement_time", [])
    curr_values = data.get("OD", [])

    if not curr_times or not curr_values:
        return 0

    if is_first:
        new_entries = list(zip(curr_times, curr_values))
    else:
        prev = _load_last_published()
        prev_data = prev.get(unit, {}).get("measurements_aggregated", {}).get("OD", {})
        prev_times = prev_data.get("measurement_time", [])
        new_entries = find_new_entries(prev_times, curr_times, curr_values)

    if not new_entries:
        return 0

    topic = f"pioreactor/{unit}/{experiment}/od_reading/od2"
    for t, v in new_entries:
        ts_dt = measurement_time_to_datetime(start_datetime, t)
        payload = json.dumps({
            "calibrated": 0,
            "timestamp": ts_dt.isoformat(),
            "angle": "90",
            "od": v,
            "channel": "2",
            "ir_led_intensity": 80.0,
        })
        client.publish(topic, payload, qos=1, retain=False)

    log.info(f"{unit}/od_reading/od2: {len(new_entries)} new points")
    return len(new_entries)


WASTE_REMOVAL_RATIO = float(os.environ.get("WASTE_REMOVAL_RATIO", "2.0"))


def publish_dosing_event(client, unit, experiment, data, start_datetime, is_first):
    """Publish feed pulses as dosing_events to MQTT for mqtt_to_db_streaming.

    For each add_media pulse, a remove_waste event is emitted to keep volume balanced.
    Waste volume = add_media volume * WASTE_REMOVAL_RATIO.
    """
    curr_times = data.get("measurement_time", [])
    curr_volumes = data.get("Feed_meas", [])

    if not curr_times or not curr_volumes:
        return 0

    if is_first:
        new_entries = list(zip(curr_times, curr_volumes))
    else:
        prev = _load_last_published()
        prev_feed = prev.get(unit, {}).get("measurements_aggregated", {}).get("Feed_meas", {})
        prev_times = prev_feed.get("measurement_time", [])
        new_entries = find_new_entries(prev_times, curr_times, curr_volumes)

    if not new_entries:
        return 0

    topic = f"pioreactor/{unit}/{experiment}/dosing_events"
    for t, volume in new_entries:
        ts_dt = measurement_time_to_datetime(start_datetime, t)

        add_payload = json.dumps({
            "timestamp": ts_dt.isoformat(),
            "volume_change": volume,
            "event": "add_media",
            "source_of_event": "dosing_automation",
        })
        client.publish(topic, add_payload, qos=1, retain=False)

        waste_payload = json.dumps({
            "timestamp": ts_dt.isoformat(),
            "volume_change": volume * WASTE_REMOVAL_RATIO,
            "event": "remove_waste",
            "source_of_event": "dosing_automation",
        })
        client.publish(topic, waste_payload, qos=1, retain=False)

    log.info(f"{unit}/dosing_events: {len(new_entries)} add+remove pulses published")
    return len(new_entries) * 2


MEASUREMENT_HANDLERS = {
    "OD": publish_od_reading,
    "Feed_meas": publish_dosing_event,
}


# ---------------------------------------------------------------------------
# Bioreactor retained state cleanup
# ---------------------------------------------------------------------------

BIOREACTOR_RETAINED_TOPICS = [
    "bioreactor/cumulative_media_added_ml",
    "bioreactor/cumulative_alt_media_added_ml",
    "bioreactor/cumulative_waste_removed_ml",
    "bioreactor/current_volume_ml",
    "bioreactor/alt_media_fraction",
]

AUTOMATION_JOB_NAMES = [
    "monitor", "stirring", "od_reading", "temperature_automation",
    "growth_rate_calculating", "dosing_automation", "led_automation",
    "add_media", "add_alt_media", "remove_waste",
]


def _clear_automation_lost_states(client, experiment, unit_list):
    """Subscribe to all unit/experiment topics and publish empty to any $state topic."""
    cleared = 0
    for unit in unit_list:
        sub_topic = f"pioreactor/{unit}/{experiment}/#"
        received = []

        def on_message(c, userdata, msg):
            if msg.topic.endswith("/$state") and msg.payload:
                received.append(msg.topic)

        client.subscribe(sub_topic, qos=1)
        client.on_message = on_message
        client.loop()
        time.sleep(0.5)
        client.loop()

        for topic in received:
            client.publish(topic, "", qos=1, retain=True)
            cleared += 1

        client.unsubscribe(sub_topic)

    return cleared


def clear_bioreactor_retained_state(experiment: str, unit_list: list[str]) -> None:
    """Clear stale retained MQTT values: bioreactor state + automation $state topics.

    Runs multiple passes to ensure the monitor's re-publishes are overwritten.
    """
    for attempt in range(3):
        client = mqtt.Client(client_id=f"emulator_clear_{os.getpid()}_{attempt}", protocol=mqtt.MQTTv5)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        for unit in unit_list:
            for suffix in BIOREACTOR_RETAINED_TOPICS:
                topic = f"pioreactor/{unit}/{experiment}/{suffix}"
                client.publish(topic, "0", qos=1, retain=True)

        cleared = _clear_automation_lost_states(client, experiment, unit_list)

        client.loop_stop()
        client.disconnect()

        if attempt < 2:
            time.sleep(1)

    log.info(f"Cleared retained bioreactor state + {cleared} automation $state topics for {', '.join(unit_list)}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def save_measurements(start_datetime):
    if isinstance(start_datetime, str):
        start_datetime = datetime.fromisoformat(start_datetime).replace(tzinfo=timezone.utc)

    config_path = os.environ.get("CONFIG_PATH", "/app/model/EMULATOR_config.json")
    with open(config_path) as f:
        emulator_config = json.load(f)

    exp_name = emulator_config["exp_name"]
    mbr_list = emulator_config["Brxtor_list"]

    input_path = os.environ.get("DB_EMULATOR_PATH", os.path.join(MODEL_DIR, "db_emulator.json"))

    if not os.path.exists(input_path):
        log.warning(f"Input file not found: {input_path}")
        return 0

    with open(input_path) as f:
        curr = json.load(f)

    prev = _load_last_published()
    is_first = prev is None

    if is_first:
        log.info("First iteration: all data is new")

    client = mqtt.Client(client_id=f"emulator_{os.getpid()}", protocol=mqtt.MQTTv5)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    total_published = 0

    for unit in mbr_list:
        if unit not in curr:
            log.warning(f"Unit '{unit}' not found in data, skipping")
            continue

        measurements = curr[unit].get("measurements_aggregated", {})

        for measurement, data in measurements.items():
            handler = MEASUREMENT_HANDLERS.get(measurement)
            if handler is None:
                continue
            total_published += handler(client, unit, exp_name, data, start_datetime, is_first)

    client.loop_stop()
    client.disconnect()

    _save_last_published(curr)

    log.info(f"Published {total_published} points total")
    return total_published
