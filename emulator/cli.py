#!/usr/bin/env python3
"""CLI for the Pioreactor Emulator Service."""

import sys
import os
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("emulator.cli")


def cmd_start(args):
    from emulator.pidfile import clear_stop_flag, is_running, PID_FILE
    from emulator.main import run

    if is_running():
        log.error("Emulator already running")
        sys.exit(1)

    clear_stop_flag()
    run(start_from_checkpoint=args.resume)


def cmd_stop(args):
    from emulator.pidfile import request_stop
    request_stop()
    log.info("Stop flag written — emulator will exit on next loop iteration")


def cmd_status(args):
    from emulator.pidfile import is_running, get_pid

    if is_running():
        pid = get_pid()
        print(f"Emulator is RUNNING (PID {pid})")
    else:
        print("Emulator is STOPPED")


def cmd_reset(args):
    state_dir = os.environ.get("STATE_DIR", "/app/state")
    model_dir = os.environ.get("MODEL_DIR", "/app/model")

    for fname in ["EMULATOR_state.json", "EMULATOR_design.json", "EMULATOR_prediction.json",
                   "db_emulator.json", "start_datetime", "emulator.pid", "stopped",
                   "last_published.json"]:
        path = os.path.join(state_dir, fname)
        if os.path.exists(path):
            os.remove(path)
            log.info(f"Removed {fname}")

    # Model-generated runtime files (never the sources / EMULATOR_config.json)
    for fname in ["EMULATOR_state.json", "EMULATOR_design.json", "db_emulator.json",
                   "measurements_atline.csv"]:
        path = os.path.join(model_dir, fname)
        if os.path.exists(path):
            os.remove(path)
            log.info(f"Removed model/{fname}")

    log.info("Reset complete")


def main():
    parser = argparse.ArgumentParser(description="Pioreactor Emulator Service")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start the emulator")
    p_start.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="Stop the emulator gracefully")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="Check if emulator is running")
    p_status.set_defaults(func=cmd_status)

    p_reset = sub.add_parser("reset", help="Reset emulator state (clear all data)")
    p_reset.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
