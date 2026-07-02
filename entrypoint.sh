#!/bin/bash
set -e

DB="/home/pioreactor/.pioreactor/storage/pioreactor.sqlite"
CAL_DIR="/home/pioreactor/.pioreactor/storage/calibrations"
SQL_DIR="/app/packaging/shared-assets/sql"
HARDWARE_DIR="/home/pioreactor/.pioreactor/hardware"

# Crear archivos de configuración de hardware (ausentes en emulación sin HAT real)
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

# Inicializar base de datos si no existe
if [ ! -f "$DB" ]; then
  echo "Inicializando base de datos..."
  python3 -c "
import sqlite3, os
conn = sqlite3.connect(os.environ['DB'])
for f in ['sqlite_configuration.sql', 'create_tables.sql', 'create_triggers.sql']:
    conn.executescript(open(f'{os.environ[\"SQL_DIR\"]}/{f}').read())
conn.close()
"
fi

# Asegurar ownership del volume montado para el usuario pioreactor
chown -R pioreactor:pioreactor /home/pioreactor/.pioreactor 2>/dev/null || true

# Crear directorio de calibraciones (evita 404 en /unit_api/calibrations)
mkdir -p "$CAL_DIR"

# Fijar permisos del cache para que el usuario pioreactor (UID 1000) pueda escribir
chown -R pioreactor:pioreactor /tmp/pioreactor_cache 2>/dev/null || true

# Limpiar caches stale (locks huérfanos de corridas anteriores)
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

# Copiar descriptores YAML de UI (Activities/Settings tabs)
mkdir -p /home/pioreactor/.pioreactor/ui
cp -r /app/packaging/shared-assets/pioreactor/ui/* /home/pioreactor/.pioreactor/ui/ 2>/dev/null || true

huey_consumer pioreactor.web.tasks.huey -n -w 8 -f -C -d 0.01 &

# Esperar a que Mosquitto esté listo y luego iniciar el streaming MQTT→DB
(sleep 5 && pio run mqtt_to_db_streaming) &

/usr/sbin/sshd

exec flask --app local_app run -p 4999 --host 0.0.0.0
