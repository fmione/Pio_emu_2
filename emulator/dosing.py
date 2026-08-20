import json
import os
import logging

from emulator.db import get_dosing_events

log = logging.getLogger("emulator.dosing")


def load_and_update_design(model_dir, start_datetime, brxtor_list):
    """
    Read dosing events from Pioreactor DB and update EMULATOR_design.json
    with the latest feed profiles before each simulation step.
    """
    design_path = os.path.join(model_dir, "EMULATOR_design.json")

    if not os.path.exists(design_path):
        log.warning(f"Design file not found: {design_path}")
        return

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
        if unit not in dosing_data:
            continue
        if unit not in design:
            continue
        design[unit]["Profiles"]["time_feed"] = dosing_data[unit]["time_feed"]
        design[unit]["Profiles"]["Feed_profile"] = dosing_data[unit]["Feed_profile"]
        updated = True

    if updated:
        with open(design_path, "w") as f:
            json.dump(design, f)
