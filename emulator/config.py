import json
import os
import logging

log = logging.getLogger("emulator.config")

DEFAULT_CONFIG = os.environ.get("CONFIG_PATH", "/app/configs/EMULATOR_config.json")


def load_config(config_path=None):
    path = config_path or DEFAULT_CONFIG
    with open(path) as f:
        return json.load(f)
