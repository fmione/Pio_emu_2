#!/bin/bash
set -e

EXPERIMENT="${1:-simulation}"
API="http://localhost:4999/api"
DC="docker compose"

if ! docker ps >/dev/null 2>&1; then
  DC="sudo docker compose"
fi

echo "=== Iniciando experimento: $EXPERIMENT ==="

# 0. Limpiar jobs previos y caches stale (locks, pwms, leds)
echo "Limpiando jobs anteriores..."
$DC exec backend sh -c "pio kill --all-jobs 2>/dev/null; \
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
\"" || true

# 1. Crear el experimento
echo "Creando experimento..."
curl -s -X POST "$API/experiments" \
  -H "Content-Type: application/json" \
  -d "{\"experiment\": \"$EXPERIMENT\", \"description\": \"Simulación automática - $EXPERIMENT\"}"

# 2. Registrar workers si no existen
echo "Registrando workers..."
for w in pio01 worker01; do
  curl -s -o /dev/null -X PUT "$API/workers" \
    -H "Content-Type: application/json" \
    -d "{\"pioreactor_unit\": \"$w\", \"model_name\": \"pioreactor_20ml\", \"model_version\": \"1.1\"}"
  echo "  → $w registrado (pioreactor_20ml v1.1)"
done

# 3. Asignar worker pio01 al experimento
echo "Asignando workers..."
curl -s -X PUT "$API/experiments/$EXPERIMENT/workers" \
  -H "Content-Type: application/json" \
  -d "{\"pioreactor_unit\": \"pio01\"}"
echo "  → pio01 asignado"

# 3. Ejecutar el profile
echo "Ejecutando experiment profile..."
$DC exec backend bash -c "EXPERIMENT=$EXPERIMENT pio run experiment_profile execute \
  /home/pioreactor/.pioreactor/experiment_profiles/simulate.yaml \"$EXPERIMENT\""

echo "=== Experimento $EXPERIMENT iniciado ==="
