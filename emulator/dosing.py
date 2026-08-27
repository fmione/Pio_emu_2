import hashlib
import json
import os
import logging
import sys

from emulator.db import get_dosing_events, _get_config

log = logging.getLogger("emulator.dosing")

DEFAULT_YAML_PATH = "/home/pioreactor/.pioreactor/experiment_profiles/profile_update.yaml"

# Cache of the last converted YAML profile: pulses are anchored to the
# simulation time at which the file content was first seen, so repeated
# reads do not push the scheduled doses forward in time.
_yaml_cache = {"hash": None, "mtime": None, "profiles": None, "warned": None}


def _get_acceleration():
    try:
        return float(_get_config().get("acceleration", 1))
    except Exception:
        return 1.0


def _get_sim_time(model_dir):
    try:
        with open(os.path.join(model_dir, "EMULATOR_state.json")) as f:
            return float(json.load(f)["time"])
    except Exception:
        return None


def _import_yaml_to_profile(model_dir):
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    from function_aux_profile import yaml_to_profile

    return yaml_to_profile


def _load_yaml_profile(model_dir, brxtor_list, sim_time):
    """
    Load feed pulses from profile_update.yaml (times relative to the moment
    the file was written). The file is re-anchored to the current simulation
    time only when its content changes; between changes the cached absolute
    pulses are reused.
    """
    yaml_path = os.environ.get("PROFILE_YAML_PATH", DEFAULT_YAML_PATH)

    if not os.path.exists(yaml_path):
        if _yaml_cache["warned"] != "missing":
            log.warning(f"Feed profile YAML not found: {yaml_path}")
            _yaml_cache["warned"] = "missing"
        return None

    with open(yaml_path, "rb") as f:
        content = f.read()
    digest = hashlib.md5(content).hexdigest()
    mtime = os.path.getmtime(yaml_path)

    if digest == _yaml_cache["hash"] and mtime == _yaml_cache["mtime"]:
        return _yaml_cache["profiles"]

    try:
        yaml_to_profile = _import_yaml_to_profile(model_dir)
        profiles = {}
        for unit in brxtor_list:
            profiles[unit] = yaml_to_profile(
                yaml_path, time_current=sim_time, pioreactor_list=[unit]
            )[unit]
    except Exception as e:
        if _yaml_cache["warned"] != digest:
            log.warning(f"Failed to parse feed profile YAML {yaml_path}: {e}")
            _yaml_cache["warned"] = digest
        return None

    _yaml_cache["hash"] = digest
    _yaml_cache["mtime"] = mtime
    _yaml_cache["profiles"] = profiles
    _yaml_cache["warned"] = None
    parts = [f"{u}={len(p['time_feed'])} pulses" for u, p in profiles.items()]
    log.info(
        f"Loaded feed profile from YAML (anchored at sim_time={sim_time:.4f}h): "
        f"{', '.join(parts)}"
    )
    return profiles


def _merge_profiles(existing, new, sim_time):
    """Keep pulses already reached by the simulation and add the new ones without duplicating."""
    past = [
        (t, v)
        for t, v in zip(existing["time_feed"], existing["Feed_profile"])
        if t <= sim_time
    ]
    past_set = set(past)
    future = [
        (t, v)
        for t, v in zip(new["time_feed"], new["Feed_profile"])
        if (t, v) not in past_set
    ]
    merged = sorted(past + future)
    return {
        "time_feed": [t for t, _ in merged],
        "Feed_profile": [v for _, v in merged],
    }


def load_and_update_design(model_dir, start_datetime, brxtor_list):
    """
    Update EMULATOR_design.json with the latest feed profiles before each
    simulation step.

    acceleration == 1: read dosing events from the Pioreactor DB.
    acceleration != 1: read pulses from profile_update.yaml via the model's
    yaml_to_profile (times relative to the current simulation time).
    """
    design_path = os.path.join(model_dir, "EMULATOR_design.json")

    if not os.path.exists(design_path):
        log.warning(f"Design file not found: {design_path}")
        return

    acceleration = _get_acceleration()

    sim_time = None
    if acceleration != 1:
        sim_time = _get_sim_time(model_dir)
        if sim_time is None:
            log.warning("EMULATOR_state.json missing or invalid, skipping feed profile update")
            return
        dosing_data = _load_yaml_profile(model_dir, brxtor_list, sim_time)
    else:
        dosing_data = get_dosing_events(start_datetime)

    if not dosing_data:
        return

    try:
        with open(design_path) as f:
            design = json.load(f)
    except Exception as e:
        log.warning(f"Failed to read design file: {e}")
        return

    updated = False
    for unit in brxtor_list:
        if unit not in dosing_data or unit not in design:
            continue
        if sim_time is None:
            new_times = dosing_data[unit]["time_feed"]
            new_volumes = dosing_data[unit]["Feed_profile"]
        else:
            merged = _merge_profiles(design[unit]["Profiles"], dosing_data[unit], sim_time)
            new_times = merged["time_feed"]
            new_volumes = merged["Feed_profile"]

        if (
            design[unit]["Profiles"]["time_feed"] != new_times
            or design[unit]["Profiles"]["Feed_profile"] != new_volumes
        ):
            design[unit]["Profiles"]["time_feed"] = new_times
            design[unit]["Profiles"]["Feed_profile"] = new_volumes
            updated = True

    if updated:
        with open(design_path, "w") as f:
            json.dump(design, f)
