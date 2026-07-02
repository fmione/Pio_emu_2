# PioDocker — Pioreactor Local Emulator

Propósito: Emular localmente (vía Docker) el stack completo de Pioreactor sin
hardware Raspberry Pi. Usar `TESTING=1` para sustituir GPIO/I2C/ADC.

## Stack emulado

| Servicio       | Tecnología             |
|----------------|------------------------|
| MQTT broker    | Eclipse Mosquitto      |
| Tareas async   | Huey + SqliteHuey      |
| Backend API    | Flask (puerto 4999)    |
| Workers        | Python 3.13+           |
| Frontend       | React (desde Flask)    |
| Base de datos  | SQLite (en volumen)    |

## Arquitectura

- `docker-compose.yml` orquesta mosquitto + backend.
- El backend corre con `TESTING=1` y `config.ini` (basado en `config.dev.ini` del upstream).
- Los workers se ejecutan como procesos dentro del contenedor backend,
  lanzados vía `pio run` o la API HTTP.
- MQTT es el bus de mensajes entre workers y UI.
- Huey usa **SqliteHuey** (archivo SQLite local), **no Redis**.
- El frontend React (pre-compilado) es servido por Flask en el puerto 4999.
  No hay contenedor frontend separado.

## Comandos de desarrollo

- `docker compose up --build` — levanta todo el stack.
- `docker compose exec backend pytest core/tests` — ejecutar tests.
- `docker compose exec backend pio run <job>` — lanzar job manualmente.
- `docker compose exec backend pio logs -n 10` — ver logs recientes.
- `docker compose exec backend pio mqtt` — ver feed MQTT en vivo.
- `./simulate.sh [experimento]` — crear experimento y lanzar simulación (stirring 500, temp 30°C, OD LED 80%).

## Archivos del proyecto

| Archivo | Propósito |
|---|---|
| `docker-compose.yml` | Orquesta mosquitto + backend |
| `Dockerfile.backend` | Imagen Python 3.13-slim con Pioreactor |
| `entrypoint.sh` | Lanza Huey consumer + Flask API + MQTT→DB streaming |
| `simulate.sh` | Script para lanzar simulación manual |
| `mosquitto/mosquitto.conf` | Config Mosquitto (anon, MQTT + WS) |
| `.pioreactor/config.ini` | Config Pioreactor (broker→`mosquitto`) |
| `.pioreactor/experiment_profiles/simulate.yaml` | Perfil de experimento para simulación |

## Referencias

- Repo upstream: https://github.com/Pioreactor/pioreactor
- Docs desarrollo local: https://docs.pioreactor.com/developer-guide/local-development
- Config dev: `config.dev.ini` del upstream
