import json
import os
import logging
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
STATE_DIR = os.environ.get("STATE_DIR", "/app/state")

MEASUREMENT_MAP = {
    "Xv": {
        "topic_suffix": "od_reading/od2",
        "payload_key": "od",
        "parser": "parse_od",
    },
    "OD600": {
        "topic_suffix": "od_reading/od_fused",
        "payload_key": "od_fused",
        "parser": None,
    },
    "Temperature": {
        "topic_suffix": "temperature_automation/temperature",
        "payload_key": "temperature",
        "parser": "parse_temperature",
    },
    "Glucose": {
        "topic_suffix": "bioreactor/glucose",
        "payload_key": "glucose",
        "parser": None,
    },
    "Feed_meas": {
        "topic_suffix": "bioreactor/feed_meas",
        "payload_key": "feed_meas",
        "parser": None,
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("emulator.mqtt")


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


def measurement_time_to_datetime(start_datetime: datetime, mt_hours: float) -> datetime:
    return start_datetime + timedelta(hours=mt_hours)


def build_payload(measurement: str, value: float, timestamp_dt: datetime) -> str | None:
    config = MEASUREMENT_MAP.get(measurement)
    if config is None:
        return None

    ts = timestamp_dt.isoformat()

    if config["parser"] == "parse_od":
        return json.dumps({
            "calibrated": 0,
            "timestamp": ts,
            "angle": "90",
            "od": value,
            "channel": "2",
            "ir_led_intensity": 80.0,
        })
    elif config["parser"] == "parse_od_fused":
        return json.dumps({"od_fused": value, "timestamp": ts})
    elif config["parser"] == "parse_temperature":
        return json.dumps({"temperature": value, "timestamp": ts})
    else:
        return json.dumps({config["payload_key"]: value, "timestamp": ts})


def publish_measurement(
    client: mqtt.Client,
    unit: str,
    experiment: str,
    measurement: str,
    value: float,
    timestamp_dt: datetime,
) -> None:
    config = MEASUREMENT_MAP.get(measurement)
    if config is None:
        return

    topic = f"pioreactor/{unit}/{experiment}/{config['topic_suffix']}"
    payload = build_payload(measurement, value, timestamp_dt)
    if payload is None:
        return

    client.publish(topic, payload, qos=1, retain=False)


def find_new_entries(prev_times, curr_times, curr_values):
    prev_set = set(prev_times)
    return [(t, v) for t, v in zip(curr_times, curr_values) if t not in prev_set]


def save_measurements(start_datetime):
    if isinstance(start_datetime, str):
        start_datetime = datetime.fromisoformat(start_datetime).replace(tzinfo=timezone.utc)

    config_path = os.environ.get("CONFIG_PATH", "/app/configs/EMULATOR_config.json")
    with open(config_path) as f:
        emulator_config = json.load(f)

    exp_name = emulator_config["exp_name"]
    mbr_list = emulator_config["Brxtor_list"]
    OD_factor = emulator_config["OD_factor"]

    input_path = os.environ.get("DB_EMULATOR_PATH", os.path.join(STATE_DIR, "db_emulator.json"))

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
            curr_times = data.get("measurement_time", [])
            curr_values = data.get(measurement, [])

            if not curr_times or not curr_values:
                continue

            if is_first:
                new_entries = list(zip(curr_times, curr_values))
            else:
                prev_data = prev.get(unit, {}).get("measurements_aggregated", {}).get(measurement, {})
                prev_times = prev_data.get("measurement_time", [])
                new_entries = find_new_entries(prev_times, curr_times, curr_values)

            if not new_entries:
                continue

            log.info(f"{unit}/{measurement}: {len(new_entries)} new points")

            for t, v in new_entries:
                ts_dt = measurement_time_to_datetime(start_datetime, t)
                publish_value = v * OD_factor.get(unit, 1.0) if measurement == "Xv" else v
                publish_measurement(client, unit, exp_name, measurement, publish_value, ts_dt)
                total_published += 1

    client.loop_stop()
    client.disconnect()

    _save_last_published(curr)

    log.info(f"Published {total_published} points total")
    return total_published
