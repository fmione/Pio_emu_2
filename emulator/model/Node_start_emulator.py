import json
import time


def start_EXP():
    """Initialize all emulator JSON state files from configuration and template."""

    # Load template database and configuration
    with open('db_emulator_template.json') as json_file:
        db_emulator_template = json.load(json_file)

    with open('EMULATOR_config.json') as json_file:
        EMULATOR_config = json.load(json_file)

    brxtor_list = EMULATOR_config['Brxtor_list']
    species_list = EMULATOR_config['Species_list']

    # Build initial state
    EMULATOR_state = {'time_absolute': time.time(), 'time': 0, 'iter': 0}

    for i1 in brxtor_list:
        EMULATOR_state[i1] = {'All': {}, 'Sample': {}, 'Current': {}, 'Prediction': {}}

        for i2 in species_list:
            ic_value = EMULATOR_config[i1]['IC'][i2]
            EMULATOR_state[i1]['All'][i2] = {'time': [0], 'Value': [ic_value]}
            EMULATOR_state[i1]['Sample'][i2] = {'time': [], 'Value': []}
            EMULATOR_state[i1]['Current'][i2] = ic_value

    # Build initial design
    EMULATOR_design = {'time_start_absolute': EMULATOR_state['time_absolute']}
    for i1 in brxtor_list:
        EMULATOR_design[i1] = {
            'Profiles': {
                'time_feed': EMULATOR_config[i1]['Feed_profile']['time_feed'],
                'Feed_profile': EMULATOR_config[i1]['Feed_profile']['Feed_profile'],
                'time_sample': EMULATOR_config[i1]['time_sample'],
            },
            'time_sample': {},
            'Glucose_feed': EMULATOR_config[i1]['Glucose_feed'],
        }
        for i2 in EMULATOR_config['Species_regression']:
            EMULATOR_design[i1]['time_sample'][i2] = EMULATOR_config[i1]['time_sample'][i2]

    # Persist all files
    with open('EMULATOR_state.json', "w") as outfile:
        json.dump(EMULATOR_state, outfile)
    with open('EMULATOR_design.json', "w") as outfile:
        json.dump(EMULATOR_design, outfile)
    with open('db_emulator.json', "w") as outfile:
        json.dump(db_emulator_template, outfile)

if __name__ == "__main__":
    start_EXP()
