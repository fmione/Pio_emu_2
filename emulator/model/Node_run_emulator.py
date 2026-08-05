import json
import time

import method_emulator

from pathlib import Path


def run_emu():
    """Run a single simulation step: read state, simulate, sample, and persist results."""

    # Load current state, design, config, and database
    with open('EMULATOR_state.json') as json_file:
        EMULATOR_state = json.load(json_file)
    with open('EMULATOR_design.json') as json_file:
        EMULATOR_design = json.load(json_file)
    with open('EMULATOR_config.json') as json_file:
        EMULATOR_config = json.load(json_file)
    with open('db_emulator.json') as json_file:
        db_emulator = json.load(json_file)

    # Determine time bounds
    time_final_absolute = time.time()

    if len(EMULATOR_config['time_execution']) == 0:
        # Real-time mode: scale wall clock by acceleration factor
        time_initial_absolute = EMULATOR_state['time_absolute']
        time_start_absolute = EMULATOR_design['time_start_absolute']
        time_initial = EMULATOR_config['acceleration'] * (time_initial_absolute - time_start_absolute) / 3600
        time_final = EMULATOR_config['acceleration'] * (time_final_absolute - time_start_absolute) / 3600
    else:
        # Discrete time-step mode using pre-defined execution schedule
        time_initial = float(EMULATOR_config['time_execution'][EMULATOR_state['iter']])
        time_final = float(EMULATOR_config['time_execution'][EMULATOR_state['iter'] + 1])

    # Max acceleration: run the entire experiment in one step
    if EMULATOR_config['acceleration'] == 54000:
        time_initial = 0
        time_final = EMULATOR_config['experiment_duration']

    # Update absolute reference time
    EMULATOR_state['time_absolute'] = time_final_absolute
    EMULATOR_state['time'] = time_final

    # Read feeding profile from controller output (DTWIN_design.json)
    try:
        design_file = str(Path.cwd().parent) + '/controller_dag/' + 'DTWIN_design.json'
        with open(design_file) as json_file:
            DTWIN_design_profile = json.load(json_file)
        for i1 in EMULATOR_config['Brxtor_list']:
            EMULATOR_design[i1]['Profiles']['time_feed'] = DTWIN_design_profile[i1]['Profiles']['time_feed']
            EMULATOR_design[i1]['Profiles']['Feed_profile'] = DTWIN_design_profile[i1]['Profiles']['Feed_profile']
    except Exception:
        pass

    # Persist the updated design
    with open('EMULATOR_design.json', "w") as outfile:
        json.dump(EMULATOR_design, outfile)

    # print(time_initial, time_final)

    # Step 1: Simulate ODE
    NEW_EMULATOR_state = method_emulator.simulate(time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config)

    # Step 2: Sample measurements with noise
    NEW_EMULATOR_state = method_emulator.sample(time_initial, time_final, NEW_EMULATOR_state, EMULATOR_design, EMULATOR_config)

    # Step 3: Write results to database JSON
    method_emulator.write('db_emulator.json', time_initial, time_final, NEW_EMULATOR_state, EMULATOR_design, EMULATOR_config)
    method_emulator.write_csv('measurements_atline.csv', NEW_EMULATOR_state, EMULATOR_design, EMULATOR_config)
    # Persist updated state
    with open('EMULATOR_state.json', "w") as outfile:
        json.dump(NEW_EMULATOR_state, outfile)


if __name__ == "__main__":
    run_emu()
    with open('EMULATOR_state.json') as json_file:
        CONTROL_state = json.load(json_file)
    i1 = 'pio01'
    tt = CONTROL_state[i1]['All']['Xv']['time']
    xx = CONTROL_state[i1]['All']['Xv']['Value']
    gg = CONTROL_state[i1]['All']['Glucose']['Value']
