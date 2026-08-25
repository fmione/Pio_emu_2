import json
import os
import sys
import time
import logging

from emulator.config import load_config
from emulator.mqtt import save_measurements, clear_bioreactor_retained_state
from emulator.db import clean_db, init_db, clear_bioreactor_cache
from emulator.dosing import load_and_update_design
from emulator.pidfile import write_pid, remove_pid, should_stop, clear_stop_flag

log = logging.getLogger("emulator.main")

STATE_DIR = os.environ.get("STATE_DIR", "/app/state")
MODEL_DIR = os.environ.get("MODEL_DIR", "/app/model")


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


def _model_path(name):
    return os.path.join(MODEL_DIR, name)


def _load_model_json(name):
    path = _model_path(name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _load_model_modules():
    """Import the unmodified model files. They use CWD-relative paths, so we run from MODEL_DIR."""
    os.chdir(MODEL_DIR)
    if MODEL_DIR not in sys.path:
        sys.path.insert(0, MODEL_DIR)

    from Node_start_emulator import start_EXP
    from Node_run_emulator import run_emu

    return start_EXP, run_emu


def run(start_from_checkpoint=False):
    config = load_config()

    start_EXP, run_emu = _load_model_modules()

    experiment_duration = config["experiment_duration"]
    time_execution = config.get("time_execution", [])

    if not start_from_checkpoint:
        log.info("Cleaning database...")
        clean_db()

        log.info("Clearing bioreactor cache...")
        clear_bioreactor_cache(config["exp_name"])

        log.info("Initializing database...")
        start_datetime = init_db()
        _save_state("start_datetime", {"value": start_datetime})

        log.info("Clearing retained MQTT bioreactor state...")
        clear_bioreactor_retained_state(config["exp_name"], config["Brxtor_list"])

        log.info("Initializing emulator state (model)...")
        start_EXP()
        log.info("Emulator initialized at t=0")
    else:
        start_dt_data = _load_state("start_datetime")
        if start_dt_data is None:
            log.error("No start_datetime found, cannot resume")
            return
        state = _load_model_json("EMULATOR_state.json")
        if state is None:
            log.error("No model checkpoint found, cannot resume")
            return
        start_datetime = start_dt_data["value"]
        log.info(f"Resuming from checkpoint: sim_time={state['time']:.4f}h, iter={state['iter']}")

    write_pid()
    clear_stop_flag()

    interval_seconds = config.get("interval_seconds", 5)

    log.info(f"Starting simulation loop: duration={experiment_duration}h, interval={interval_seconds}s")

    try:
        while True:
            if should_stop():
                log.info("Stop flag detected, exiting gracefully")
                break

            load_and_update_design(MODEL_DIR, start_datetime, config["Brxtor_list"])
            run_emu()

            state = _load_model_json("EMULATOR_state.json")
            if state is None:
                log.error("Model state missing, aborting")
                break

            # Discrete time-step mode: the model reads `iter`/`iter+1` but never advances it.
            if time_execution and state["iter"] + 1 < len(time_execution):
                state["iter"] = state["iter"] + 1
                with open(_model_path("EMULATOR_state.json"), "w") as f:
                    json.dump(state, f)

            sim_time = state["time"]
            log.info(f"Step done: sim_time={sim_time:.4f}h / {experiment_duration}h")

            save_measurements(start_datetime)

            if sim_time >= experiment_duration:
                log.info(f"Experiment complete: sim_time={sim_time:.4f}h >= {experiment_duration}h")
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        remove_pid()
        log.info("Emulator stopped")
