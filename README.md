# PioDocker

Local Docker environment for the full [Pioreactor](https://pioreactor.com/) stack — an open-source bioreactor for microbial cultivation — without needing any Raspberry Pi hardware.

## What is this?

Pioreactor is an automated bioreactor platform that normally runs its software on a Raspberry Pi with custom HAT hardware. **PioDocker** recreates the entire software stack — including leader/worker cluster topology, web UI, MQTT message bus, job scheduler, and experiment profiles — running entirely in Docker containers with `TESTING=1`, which substitutes GPIO, I2C, ADC, and other hardware interfaces with simulated implementations.

## Architecture

The system consists of 3 Docker services connected via a shared `lab-network`:

- **mosquitto** — MQTT broker (Eclipse Mosquitto). Acts as the central message bus. All job commands, sensor data, OD readings, dosing events, and logs flow through MQTT topics in the format `pioreactor/{unit}/{experiment}/{job}/{metric}`.

- **backend (pio01)** — Cluster leader. Runs Flask (API + pre-compiled React SPA) on port 4999, SSH on 2222, a Huey consumer (8 workers) for background tasks, and an MQTT-to-DB streaming process that persists data to SQLite.

- **worker01** — Remote worker. Runs Flask on port 4999, SSH on 2223, and a Huey consumer (4 workers). Does not initialize the main database or run MQTT-to-DB streaming. Communicates with the leader exclusively via MQTT.

The **leader** orchestrates experiments: assigns jobs to itself and workers via HTTP (`/unit_api/jobs/run/...`) or MQTT. The React frontend is served as static files from Flask, and the browser connects to the MQTT broker via WebSocket on port 9001.

## Prerequisites

- Docker and Docker Compose installed
- Create the external network before starting:
  ```bash
  docker network create lab-network
  ```

## Quick start

```bash
# Create the network (if it doesn't exist)
docker network create lab-network

# Build and start the full stack
docker compose up --build
```

Access the UI at: **http://localhost:4999**

## Services

| Service | Port(s) | Role | Volumes |
|---|---|---|---|
| `mosquitto` | 1883 (MQTT TCP), 9001 (MQTT WebSocket) | MQTT message broker | `mosquitto/mosquitto.conf` |
| `backend` | 4999 (Flask/UI), 2222 (SSH) | Leader pio01 — API, UI, jobs, DB streaming | `.pioreactor/` |
| `worker01` | 4999 (Flask), 2223 (SSH) | Worker — executes assigned jobs | `.pioreactor-worker/` |

## Configuration

### Key environment variables

| Variable | Value | Purpose |
|---|---|---|
| `TESTING` | `1` | Enables mock hardware (GPIO/I2C/ADC) |
| `HOSTNAME` | `pio01` / `worker01` | Identifies the unit |
| `MODEL_NAME` | `pioreactor_20ml` | Bioreactor model |
| `MODEL_VERSION` | `1.1` | Model version |
| `HARDWARE` | `1.2` | Hardware hat version |
| `BLINKA_FORCECHIP` | `BCM2XXX` | Forces Blinka to use RPi chip profile |
| `BLINKA_FORCEBOARD` | `RASPBERRY_PI_3A_PLUS` | Forces Blinka to use RPi board profile |

### Configuration files

- **`.pioreactor/config.ini`** — Leader configuration.
- **`.pioreactor-worker/config.ini`** — Worker configuration (same structure, `cluster.topology.leader_address=backend`).
- **`mosquitto/mosquitto.conf`** — MQTT broker: ports 1883/9001, anonymous access, persistence enabled.

### MQTT connection

- Broker: `mosquitto` (Docker DNS, rewritten to `localhost` for browser access)
- TCP: port 1883 | WebSocket: port 9001
- Mosquitto allows anonymous access by default

## Usage

### Running experiments

Experiment profiles are located in `.pioreactor/experiment_profiles/`:

- **`profile_initial.yaml`** — Stirring (500 RPM), thermostat (30°C), and OD reading
- **`profile_dosing.yaml`** — Adds media dosing (0.5ml) and waste removal (1.0ml) hourly

```bash
docker compose exec backend pio run experiment_profile execute .pioreactor/experiment_profiles/profile_initial.yaml <experiment_name>
```

### CLI commands

```bash
docker compose exec backend pio run <job_name>
docker compose exec backend pio kill --all-jobs
docker compose exec backend pio logs -n 10
docker compose exec backend pio mqtt
```

### Testing

```bash
docker compose exec backend pytest core/tests
```

### SSH access

```bash
ssh -p 2222 pioreactor@localhost   # backend
ssh -p 2223 pioreactor@localhost   # worker01
```

## Gotchas

1. **External network required**: `docker network create lab-network` must exist before `docker compose up`.
2. **MQTT address rewriting**: `local_app.py` rewrites `broker_address=mosquitto` → `broker_address=localhost` in `/api/config/shared` so the browser can reach the WebSocket on `:9001`.
3. **Ephemeral state**: Entrypoints regenerate hardware YAML, DB, calibrations, and UI descriptors on every start. Only `config.ini` is tracked in git.
4. **Upstream patches**: Dockerfiles patch `export_experiment_data.py` to use `DOT_PIOREACTOR` instead of relative paths.

## Credits

Based on the open-source [Pioreactor](https://github.com/Pioreactor/pioreactor) software.
