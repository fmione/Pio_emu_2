#!/bin/bash
set -e

EMULATOR_UID="${EMULATOR_UID:-1000}"
chown -R ${EMULATOR_UID}:${EMULATOR_UID} /app/model
smbd --daemon

STATE_DIR="${STATE_DIR:-/app/state}"
START_DT_FILE="$STATE_DIR/start_datetime"
STOP_FLAG="$STATE_DIR/stopped"

# 1. Si existe el flag de stop, quedarse idle
if [ -f "$STOP_FLAG" ]; then
    echo "Stop flag found — emulator was manually stopped. Staying idle."
    exec sleep infinity
fi

# 2. Si no existe start_datetime, nunca se inició — idle
if [ ! -f "$START_DT_FILE" ]; then
    echo "No start_datetime found — emulator has never been started. Staying idle."
    exec sleep infinity
fi

# 3. Verificar si el experimento aún está dentro del horizonte
CAN_CONTINUE=$(python3 -c "
import json, time, os
from datetime import datetime, timezone

state_dir = '$STATE_DIR'
model_dir = os.environ.get('MODEL_DIR', '/app/model')
config_path = os.environ.get('CONFIG_PATH', '/app/model/EMULATOR_config.json')

try:
    if not os.path.exists(os.path.join(model_dir, 'EMULATOR_state.json')):
        print('no-checkpoint')
        raise SystemExit

    with open(config_path) as f:
        config = json.load(f)

    with open(os.path.join(state_dir, 'start_datetime')) as f:
        start_dt = json.load(f)['value']

    start = datetime.fromisoformat(start_dt).replace(tzinfo=timezone.utc)
    elapsed_h = config['acceleration'] * (time.time() - start.timestamp()) / 3600

    if elapsed_h < config['experiment_duration']:
        print('yes')
    else:
        print('no')
except SystemExit:
    pass
except Exception as e:
    print(f'error: {e}', flush=True)
    print('no')
" 2>&1)

if [ "$CAN_CONTINUE" = "yes" ]; then
    echo "Experiment in progress — waiting for MQTT infrastructure..."
    sleep 10
    echo "Resuming emulator from checkpoint"
    exec python3 -m emulator.cli start --resume
elif [ "$CAN_CONTINUE" = "no-checkpoint" ]; then
    echo "No model checkpoint found — stale state from a previous version. Staying idle."
    exec sleep infinity
else
    echo "Experiment complete or invalid ($CAN_CONTINUE) — staying idle"
    exec sleep infinity
fi
