# PioDocker — Pioreactor Local Emulator

Purpose: Locally emulate via Docker the full Pioreactor stack without
Raspberry Pi hardware. Use `TESTING=1` to substitute GPIO/I2C/ADC.

## Emulated stack

| Service        | Technology             |
|----------------|------------------------|
| MQTT broker    | Eclipse Mosquitto      |
| Async tasks    | Huey + SqliteHuey      |
| Backend API    | Flask (port 4999)      |
| Workers        | Python 3.13+           |
| Frontend       | React served by Flask  |
| Database       | SQLite on volume       |

## Architecture

- `docker-compose.yml` orchestrates mosquitto + backend.
- Backend runs with `TESTING=1` and `config.ini` (based on upstream `config.dev.ini`).
- Workers run as processes inside the backend container,
  launched via `pio run` or the HTTP API.
- MQTT is the message bus between workers and the UI.
- Huey uses **SqliteHuey**, **not Redis**.
- The React frontend, pre-compiled, is served by Flask on port 4999.
  There is no separate frontend container.

## Development commands

- `docker compose up --build` — brings up the full stack.
- `docker compose exec backend pytest core/tests` — run tests.
- `docker compose exec backend pio run <job>` — launch a job manually.
- `docker compose exec backend pio logs -n 10` — view recent logs.
- `docker compose exec backend pio mqtt` — view live MQTT feed.
- `./simulate.sh [experiment]` — create experiment and start simulation (stirring 500, temp 30C, OD LED 80%).

## Project files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Orchestrates mosquitto + backend |
| `Dockerfile.backend` | Python 3.13-slim image with Pioreactor |
| `entrypoint.sh` | Launches Huey consumer + Flask API + MQTT-to-DB streaming |
| `simulate.sh` | Script to launch manual simulation |
| `mosquitto/mosquitto.conf` | Mosquitto config (anon, MQTT + WS) |
| `.pioreactor/config.ini` | Pioreactor config (broker->`mosquitto`) |
| `.pioreactor/experiment_profiles/simulate.yaml` | Experiment profile for simulation |

## References

- Upstream repo: https://github.com/Pioreactor/pioreactor
- Local development docs: https://docs.pioreactor.com/developer-guide/local-development
- Dev config: upstream `config.dev.ini`
