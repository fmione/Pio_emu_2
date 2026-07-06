#!/bin/bash
set -e

EXPERIMENT="${1:-simulation}"
API="http://localhost:4999/api"
DC="docker compose"

if ! docker ps >/dev/null 2>&1; then
  DC="sudo docker compose"
fi

echo "=== Starting experiment: $EXPERIMENT ==="

# 0. Clean previous jobs and stale caches
echo "Cleaning previous jobs..."
for container in backend worker01; do
  $DC exec "$container" sh -c "pio kill --all-jobs 2>/dev/null; \
    python3 -c \"
import sqlite3, os
db = '/home/pioreactor/.pioreactor/storage/local_intermittent_pioreactor_metadata.sqlite'
if os.path.exists(db):
    c = sqlite3.connect(db)
    c.executescript('''DELETE FROM cache_pwm_locks;
DELETE FROM cache_pwm_dc;
DELETE FROM cache_led_locks;
DELETE FROM cache_leds;
DELETE FROM cache_debounce;
DELETE FROM pio_job_metadata;''')
    c.commit()
    print('Cache cleaned')
    c.close()
\"" 2>/dev/null || true
done

# 1. Create the experiment
echo "Creating experiment..."
curl -s -X POST "$API/experiments" \
  -H "Content-Type: application/json" \
  -d "{\"experiment\": \"$EXPERIMENT\", \"description\": \"Auto simulation - $EXPERIMENT\"}"

# 2. Register workers if they do not exist
echo "Registering workers..."
for w in pio01 worker01; do
  curl -s -o /dev/null -X PUT "$API/workers" \
    -H "Content-Type: application/json" \
    -d "{\"pioreactor_unit\": \"$w\", \"model_name\": \"pioreactor_20ml\", \"model_version\": \"1.1\"}"
  echo "  -> $w registered"
done

# 3. Assign workers to the experiment
echo "Assigning workers..."
for w in pio01 worker01; do
  curl -s -o /dev/null -X PUT "$API/experiments/$EXPERIMENT/workers" \
    -H "Content-Type: application/json" \
    -d "{\"pioreactor_unit\": \"$w\"}"
  echo "  -> $w assigned"
done

# 4. Execute the experiment profile
echo "Running experiment profile..."
$DC exec backend bash -c "EXPERIMENT=$EXPERIMENT pio run experiment_profile execute \
  /home/pioreactor/.pioreactor/experiment_profiles/simulate.yaml \"$EXPERIMENT\""

echo "=== Experiment $EXPERIMENT started ==="
