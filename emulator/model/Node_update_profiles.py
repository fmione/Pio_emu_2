import hashlib
import json
import os
import logging
import time

logging.basicConfig(level=logging.INFO)

log = logging.getLogger("emulator.dosing")

DEFAULT_YAML_PATH = "/opt/airflow/experiment_profiles/profile_update.yaml"
# DEFAULT_YAML_PATH = "../controller_dag/profile_update.yaml"
DEFAULT_YAML_CACHE = {"hash": None, "mtime": None, "profiles": None}
YAML_CACHE_KEY = "yaml_cache"

_yaml_cache = dict(DEFAULT_YAML_CACHE)


def _load_yaml_cache():
    try:
        with open("EMULATOR_state.json") as f:
            state = json.load(f)
        cached = state.get(YAML_CACHE_KEY)
        if isinstance(cached, dict) and all(k in cached for k in DEFAULT_YAML_CACHE):
            return cached
    except Exception as e:
        log.debug(f"Could not load yaml cache from EMULATOR_state.json: {e}")
    return dict(DEFAULT_YAML_CACHE)


def _save_yaml_cache(cache):
    try:
        with open("EMULATOR_state.json") as f:
            state = json.load(f)
    except Exception as e:
        log.error(f"Could not read EMULATOR_state.json, skipping yaml cache save: {e}")
        return

    state[YAML_CACHE_KEY] = cache
    with open("EMULATOR_state.json", "w") as f:
        json.dump(state, f)


def _get_sim_time(epoch_time=None):
    try:
        with open('EMULATOR_design.json') as json_file:
            EMULATOR_design = json.load(json_file)
        with open('EMULATOR_config.json') as json_file:
            EMULATOR_config = json.load(json_file)

        time_start_absolute = EMULATOR_design['time_start_absolute']
        time_final_absolute = epoch_time if epoch_time else time.time()

        time_final = EMULATOR_config['acceleration'] * (time_final_absolute - time_start_absolute) / 3600
        log.info(f"SIM TIME: {time_final} - from epoch: {epoch_time}")
        return time_final
    except Exception:
        return None


def _load_yaml_profile(brxtor_list):
    from function_aux_profile import yaml_to_profile

    yaml_path = os.environ.get("PROFILE_YAML_PATH", DEFAULT_YAML_PATH)

    if not os.path.exists(yaml_path):
        log.warning(f"Feed profile YAML not found: {yaml_path}")
        return None, None

    with open(yaml_path, "rb") as f:
        content = f.read()
    digest = hashlib.md5(content).hexdigest()
    mtime = os.path.getmtime(yaml_path)

    sim_time = _get_sim_time(mtime)
    if sim_time is None:
        log.warning("Sim time missing or invalid, skipping feed profile update")
        return None, None
    
    if digest == _yaml_cache["hash"] and mtime == _yaml_cache["mtime"]:
        log.info(f"Reusing cached feed profile for {yaml_path} (unchanged)")
        return _yaml_cache["profiles"], sim_time

    try:
        profiles = {}
        for unit in brxtor_list:
            profiles[unit] = yaml_to_profile(
                yaml_path, time_current=sim_time, pioreactor_list=[unit]
            )[unit]
    except Exception as e:
        log.warning(f"Failed to parse feed profile YAML {yaml_path}: {e}")
        return None, None

    _yaml_cache["hash"] = digest
    _yaml_cache["mtime"] = mtime
    _yaml_cache["profiles"] = profiles
    parts = [f"{u}={len(p['time_feed'])} pulses" for u, p in profiles.items()]
    log.info(
        f"Loaded feed profile from YAML (anchored at sim_time={sim_time:.4f}h): "
        f"{', '.join(parts)}"
    )
    return profiles, sim_time


def _merge_profiles(existing, new, sim_time):
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


def _load_and_update_design(brxtor_list):
    design_path = "EMULATOR_design.json"

    if not os.path.exists(design_path):
        log.warning(f"Design file not found: {design_path}")
        return

    dosing_data, sim_time = _load_yaml_profile(brxtor_list)

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


def update_profiles():
    with open("EMULATOR_config.json") as f:
        config = json.load(f)

    _yaml_cache.clear()
    _yaml_cache.update(_load_yaml_cache())

    _load_and_update_design(config["Brxtor_list"])

    _save_yaml_cache(_yaml_cache)


if __name__ == "__main__":
    update_profiles()