import json
import os
import time
import logging
from copy import deepcopy

from emulator.config import load_config
from emulator.simulation.methods import simulate, sample, write_measurements
from emulator.mqtt import save_measurements
from emulator.db import clean_db, init_db
from emulator.pidfile import write_pid, remove_pid, should_stop, clear_stop_flag

log = logging.getLogger("emulator.main")

STATE_DIR = os.environ.get("STATE_DIR", "/app/state")


def _state_path(name):
    return os.path.join(STATE_DIR, name)


def _load_state(name):
    path = _state_path(name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _save_state(name, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_state_path(name), "w") as f:
        json.dump(data, f)


def _init_emulator_state(config):
    brxtor_list = config["Brxtor_list"]
    species_list = config["Species_list"]

    import time as _time
    EMULATOR_state = {"time_absolute": _time.time(), "time": 0, "iter": 0}
    EMULATOR_prediction = {}

    for i1 in brxtor_list:
        EMULATOR_state[i1] = {"All": {}, "Sample": {}, "Current": {}, "Prediction": {}}
        EMULATOR_prediction[i1] = {"Prediction": {}}

        for i2 in species_list:
            ic_value = config[i1]["IC"][i2]
            EMULATOR_state[i1]["All"][i2] = {"time": [0], "Value": [ic_value]}
            EMULATOR_state[i1]["Sample"][i2] = {"time": [], "Value": []}
            EMULATOR_state[i1]["Current"][i2] = ic_value
            EMULATOR_prediction[i1]["Prediction"][i2] = {"time": [0], "Value": [ic_value]}

        EMULATOR_state[i1]["Sample"]["Temperature"] = {"time": [], "Value": []}

    EMULATOR_design = {"time_start_absolute": EMULATOR_state["time_absolute"]}
    for i1 in brxtor_list:
        EMULATOR_design[i1] = {
            "Profiles": {
                "time_feed": config[i1]["Feed_profile"]["time_feed"],
                "Feed_profile": config[i1]["Feed_profile"]["Feed_profile"],
                "time_sample": config[i1]["time_sample"],
            },
            "time_sample": {},
            "Glucose_feed": config[i1]["Glucose_feed"],
        }
        for i2 in config["Species_regression"]:
            EMULATOR_design[i1]["time_sample"][i2] = config[i1]["time_sample"][i2]

    return EMULATOR_state, EMULATOR_design, EMULATOR_prediction


def _init_db_emulator(config):
    template_path = os.path.join(os.path.dirname(__file__), "configs", "db_emulator_template.json")
    if os.path.exists(template_path):
        with open(template_path) as f:
            template = json.load(f)
    else:
        template = {}
        for unit in config["Brxtor_list"]:
            template[unit] = {"measurements_aggregated": {}}
            for sp in config["Species_regression"]:
                template[unit]["measurements_aggregated"][sp] = {"measurement_time": [], sp: []}
            template[unit]["measurements_aggregated"]["Temperature"] = {"measurement_time": [], "Temperature": []}
            template[unit]["measurements_aggregated"]["Feed_meas"] = {"measurement_time": [], "Feed_meas": []}

    _save_state("db_emulator.json", template)


def run(start_from_checkpoint=False):
    config = load_config()

    acceleration = config["acceleration"]
    experiment_duration = config["experiment_duration"]
    brxtor_list = config["Brxtor_list"]

    if not start_from_checkpoint:
        log.info("Cleaning database...")
        clean_db()

        log.info("Initializing database...")
        start_datetime = init_db()
        _save_state("start_datetime", {"value": start_datetime})

        log.info("Initializing emulator state...")
        EMULATOR_state, EMULATOR_design, EMULATOR_prediction = _init_emulator_state(config)
        _save_state("EMULATOR_state.json", EMULATOR_state)
        _save_state("EMULATOR_design.json", EMULATOR_design)
        _save_state("EMULATOR_prediction.json", EMULATOR_prediction)
        _init_db_emulator(config)
        log.info("Emulator initialized at t=0")
    else:
        EMULATOR_state = _load_state("EMULATOR_state.json")
        if EMULATOR_state is None:
            log.error("No checkpoint found, cannot resume")
            return
        EMULATOR_design = _load_state("EMULATOR_design.json")
        start_dt_data = _load_state("start_datetime")
        if start_dt_data is None:
            log.error("No start_datetime found")
            return
        log.info(f"Resuming from checkpoint: sim_time={EMULATOR_state['time']:.4f}h, iter={EMULATOR_state['iter']}")

    write_pid()
    clear_stop_flag()

    interval_seconds = config.get("interval_seconds", 5)

    log.info(f"Starting simulation loop: acceleration={acceleration}, duration={experiment_duration}h, interval={interval_seconds}s")

    try:
        while True:
            if should_stop():
                log.info("Stop flag detected, exiting gracefully")
                break

            EMULATOR_state = _load_state("EMULATOR_state.json")
            EMULATOR_design = _load_state("EMULATOR_design.json")
            if EMULATOR_state is None or EMULATOR_design is None:
                log.error("State files missing, aborting")
                break

            time_final_absolute = time.time()
            time_start_absolute = EMULATOR_design["time_start_absolute"]

            if len(config.get("time_execution", [])) == 0:
                time_initial_absolute = EMULATOR_state["time_absolute"]
                time_initial = acceleration * (time_initial_absolute - time_start_absolute) / 3600
                time_final = acceleration * (time_final_absolute - time_start_absolute) / 3600
            else:
                iter_idx = EMULATOR_state["iter"]
                if iter_idx + 1 >= len(config["time_execution"]):
                    log.info("Experiment complete (reached end of time_execution)")
                    break
                time_initial = float(config["time_execution"][iter_idx])
                time_final = float(config["time_execution"][iter_idx + 1])

            if acceleration == 54000:
                time_initial = 0
                time_final = experiment_duration

            if time_final >= experiment_duration:
                log.info(f"Experiment complete: sim_time={time_final:.4f}h >= {experiment_duration}h")
                break

            log.info(f"Step {EMULATOR_state['iter']}: t=[{time_initial:.4f}, {time_final:.4f}]h")

            NEW_EMULATOR_state = simulate(time_initial, time_final, EMULATOR_state, EMULATOR_design, config)
            NEW_EMULATOR_state = sample(time_initial, time_final, NEW_EMULATOR_state, EMULATOR_design, config)
            write_measurements(_state_path("db_emulator.json"), time_initial, time_final, NEW_EMULATOR_state, EMULATOR_design, config)

            NEW_EMULATOR_state["time_absolute"] = time_final_absolute
            NEW_EMULATOR_state["time"] = time_final
            NEW_EMULATOR_state["iter"] = EMULATOR_state["iter"] + 1

            _save_state("EMULATOR_state.json", NEW_EMULATOR_state)

            start_dt_data = _load_state("start_datetime")
            if start_dt_data:
                start_dt = start_dt_data["value"]
                from datetime import datetime, timezone
                start_datetime = datetime.fromisoformat(start_dt).replace(tzinfo=timezone.utc)
                save_measurements(start_datetime)

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        remove_pid()
        log.info("Emulator stopped")
