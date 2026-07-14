#!/bin/bash
set -e

CAL_DIR="/home/pioreactor/.pioreactor/storage/calibrations"
SQL_DIR="/app/packaging/shared-assets/sql"
HARDWARE_DIR="/home/pioreactor/.pioreactor/hardware"

# Create hardware config files
_create_hw_yaml() {
  local dir="$1"
  mkdir -p "$dir"
  for mod in pwm adc temp gpio dac; do
    [ -f "$dir/$mod.yaml" ] && continue
    case "$mod" in
      pwm)
        cat > "$dir/$mod.yaml" <<'YAML'
controller: rpi_gpio
heater_pwm_channel: "5"
pwm_to_pin:
  "1": 17
  "2": 13
  "3": 16
  "4": 12
  "5": 18
YAML
        ;;
      adc)
        cat > "$dir/$mod.yaml" <<'YAML'
pd1:
  driver: ads1115
  address: 0x49
  channel: 0
pd2:
  driver: ads1115
  address: 0x4a
  channel: 0
aux:
  driver: ads1115
  address: 0x48
  channel: 0
version:
  driver: ads1115
  address: 0x48
  channel: 1
YAML
        ;;
      temp)
        cat > "$dir/$mod.yaml" <<'YAML'
address: 0x3A
YAML
        ;;
      gpio)
        cat > "$dir/$mod.yaml" <<'YAML'
pcb_led_pin: 4
pcb_button_pin: 27
hall_sensor_pin: 5
sda_pin: 2
scl_pin: 3
YAML
        ;;
      dac)
        cat > "$dir/$mod.yaml" <<'YAML'
address: 0x60
YAML
        ;;
    esac
  done
}

_create_hw_yaml "$HARDWARE_DIR/hats/1.2"
_create_hw_yaml "$HARDWARE_DIR/models/pioreactor_20ml/1.1"
_create_hw_yaml "$HARDWARE_DIR/models/pioreactor_40ml/1.5"

# Create calibrations directory
mkdir -p "$CAL_DIR"

# Copy UI YAML descriptors
mkdir -p /home/pioreactor/.pioreactor/ui
cp -r /app/packaging/shared-assets/pioreactor/ui/* /home/pioreactor/.pioreactor/ui/ 2>/dev/null || true

# Copy exportable dataset YAML descriptors
cp -r /app/packaging/shared-assets/pioreactor/exportable_datasets/* /home/pioreactor/.pioreactor/exportable_datasets/ 2>/dev/null || true

# Create default pump calibrations
python3 << 'PYEOF'
import sqlite3, json, os
from datetime import datetime, timezone

cache_db = '/home/pioreactor/.pioreactor/storage/local_persistent_pioreactor_metadata.sqlite'
cal_dir = '/home/pioreactor/.pioreactor/storage/calibrations'

os.makedirs(f'{cal_dir}/media_pump', exist_ok=True)
os.makedirs(f'{cal_dir}/waste_pump', exist_ok=True)

now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

for pump in ['media_pump', 'waste_pump']:
    cal_name = f'default_{pump}_cal'
    unit = 'worker01'
    yaml_content = f'''calibration_type: simple_peristaltic_pump
calibration_name: "{cal_name}"
calibrated_on_pioreactor_unit: "{unit}"
created_at: {now}
hz: 250.0
dc: 100.0
voltage: -1
x: Duration
y: Volume
curve_data_:
  type: poly
  coefficients: [0.0911, 0.0]
recorded_data:
  x: []
  y: []
'''
    with open(f'{cal_dir}/{pump}/{cal_name}.yaml', 'w') as f:
        f.write(yaml_content)

conn = sqlite3.connect(cache_db)
conn.execute('CREATE TABLE IF NOT EXISTS cache_active_calibrations (key BLOB PRIMARY KEY, value BLOB)')
for pump in ['media_pump', 'waste_pump']:
    cal_name = f'default_{pump}_cal'
    conn.execute(
        'INSERT OR REPLACE INTO cache_active_calibrations (key, value) VALUES (?, ?)',
        (pump, cal_name)
    )
conn.commit()
conn.close()
print('Default calibrations for worker01 created.')
PYEOF

# Fix ownership after creating everything
chown -R pioreactor:pioreactor /home/pioreactor/.pioreactor 2>/dev/null || true

# Fix cache permissions
chown -R pioreactor:pioreactor /tmp/pioreactor_cache 2>/dev/null || true

# Clean stale caches
python3 -c "
import sqlite3, os
db_path = '/home/pioreactor/.pioreactor/storage/local_intermittent_pioreactor_metadata.sqlite'
if os.path.exists(db_path):
    c = sqlite3.connect(db_path)
    for table in ['cache_pwm_locks', 'cache_pwm_dc', 'cache_led_locks', 'cache_leds', 'cache_debounce']:
        c.execute(f'DELETE FROM {table}')
    c.execute('DELETE FROM pio_job_metadata')
    c.commit()
    c.close()
" 2>/dev/null || true

# Clear stale MQTT retained job states (prevents "Lost" on startup)
python3 -c "
import paho.mqtt.client as mqtt
import time

cleared = set()

def on_message(client, userdata, msg):
    topic = msg.topic
    if topic not in cleared and msg.payload and topic.endswith('/\$state'):
        client.publish(topic, '', retain=True)
        cleared.add(topic)
        print(f'Cleared retained state: {topic}')

c = mqtt.Client(client_id='clear-states-worker01', protocol=mqtt.MQTTv5)
c.connect('mosquitto', 1883, 60)
c.subscribe('pioreactor/worker01/#', qos=1)
c.on_message = on_message
c.loop_start()
time.sleep(5)
c.loop_stop()
c.disconnect()
print(f'Cleared {len(cleared)} stale job states for worker01')
" 2>/dev/null || true

huey_consumer pioreactor.web.tasks.huey -n -w 4 -f -C -d 0.01 &

# Patches to disable mock data emission in TESTING mode (external data via MQTT only)
if [ "$TESTING" = "1" ]; then
  # od_reading.py: skip record_from_adc() when TESTING=1
  sed -i '/def record_from_adc(self) -> structs.ODReadings | None:/a\        if whoami.is_testing_env(): return None' \
    /app/core/pioreactor/background_jobs/od_reading.py 2>/dev/null || true

  # temperature_automation.py: skip infer_temperature() when TESTING=1
  sed -i '/def infer_temperature(self) -> None:/a\        if whoami.is_testing_env(): return' \
    /app/core/pioreactor/background_jobs/temperature_automation.py 2>/dev/null || true

  # temperature_automation.py: skip initial temperature read in on_init_to_ready()
  sed -i '/def on_init_to_ready(self) -> None:/a\        if whoami.is_testing_env(): return' \
    /app/core/pioreactor/background_jobs/temperature_automation.py 2>/dev/null || true
fi

/usr/sbin/sshd

echo "Worker01 ready on port 4999"
exec flask --app worker_app run -p 4999 --host 0.0.0.0
