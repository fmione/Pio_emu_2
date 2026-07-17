import os
import logging

log = logging.getLogger("emulator.pidfile")

STATE_DIR = os.environ.get("STATE_DIR", "/app/state")
PID_FILE = os.path.join(STATE_DIR, "emulator.pid")
STOP_FLAG = os.path.join(STATE_DIR, "stopped")


def write_pid():
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    log.info(f"PID {os.getpid()} written to {PID_FILE}")


def remove_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def is_running():
    if not os.path.exists(PID_FILE):
        return False
    if os.path.exists(STOP_FLAG):
        remove_pid()
        return False
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    if pid <= 1:
        remove_pid()
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        remove_pid()
        return False


def get_pid():
    if not os.path.exists(PID_FILE):
        return None
    with open(PID_FILE) as f:
        return int(f.read().strip())


def request_stop():
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STOP_FLAG, "w") as f:
        f.write("stop")
    log.info("Stop flag written")


def should_stop():
    return os.path.exists(STOP_FLAG)


def clear_stop_flag():
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
