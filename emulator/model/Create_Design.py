import numpy as np
import json

# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------
t_duration = 15.0
exp_name = 'Exp0H'

mbr_list = np.array(['pio01', 'worker01'])

OD_factor = {'pio01': 0.030177, 'worker01': 0.022911}

# Model species and regression (measured) species
species_list = ['Xv', 'Glucose', 'Ethanol', 'V', 'e','Si']
species_regression_list = ['Xv', 'Glucose']

mbr_group = {'pioreactors': ['pio01', 'worker01']}

# Initial conditions for [Xv, Glucose, Ethanol, V, e]
species_IC = [1.0, 2, 0, 0.011, 0,0]

# Feed profile:
time_feed = [np.arange(5, t_duration, 1), np.arange(5, t_duration, 2)]#np.array([])#np.arange(5, t_duration, 1)#

profile_design = {}
for n1,i1 in enumerate(mbr_group['pioreactors']):
    Feed_profile = time_feed[n1] * 0 + 0.5
    profile_design[i1] = {'time_feed': time_feed[n1].tolist(), 'Feed_profile': Feed_profile.tolist()}

# Measurement sampling times
time_samples = {
    'Xv': np.arange(0, t_duration, 0.01),
    'Glucose': np.arange(0.5, 5.5, 1),
}

# Measurement noise (percentage)
Noise_concentration = {    'Xv': 1/100,
                       'Glucose': 5/100}
Noise_time = 1

# Glucose feed concentration (g/L)
Glucose_feed = [2] * len(mbr_list)

# Reference kinetic parameters
Params_ref = np.array([0.39565891, 0.20655672, 1.27312121, 0.067108  , 0.31610876,
       0.38588422, 0.36423799, 0.37617746, 0.24299876, 0.00392031,
       0.07543501, 0.04302811, 0.08356779, 0.84832334, 0.60040242,
       0.63635726, 0.5526098 ])
Params = {}
for i in range(mbr_list.shape[0]):
    Params[i] = Params_ref.tolist() + [0.5, 0.5]

# Leave empty for real-time execution, otherwise provide time steps in hours
time_execution = []

# Acceleration factor: 1 = real-time, or 2, 4, 60, 54000
acceleration = 4

# ---------------------------------------------------------------------------
# Build and save configuration
# ---------------------------------------------------------------------------
EMULATOR_config = {}
EMULATOR_config['iter'] = 0
EMULATOR_config['Params'] = Params
EMULATOR_config['exp_name'] = exp_name
EMULATOR_config['OD_factor'] = OD_factor

EXP_list = [str(il) for il in mbr_list]
EMULATOR_config['Species_list'] = species_list
EMULATOR_config['Species_regression'] = species_regression_list
EMULATOR_config['Brxtor_list'] = EXP_list
EMULATOR_config['mbr_group'] = mbr_group

for i1 in EXP_list:
    EMULATOR_config[i1] = {}
    EMULATOR_config[i1]['IC'] = {}
    for idx, i2 in enumerate(EMULATOR_config['Species_list']):
        EMULATOR_config[i1]['IC'][i2] = species_IC[idx]

for idx, i1 in enumerate(EXP_list):
    EMULATOR_config[i1]['Glucose_feed'] = float(Glucose_feed[idx])
    EMULATOR_config[i1]['Feed_profile'] = {
        'time_feed': profile_design[i1]['time_feed'],
        'Feed_profile': profile_design[i1]['Feed_profile'],
    }
    EMULATOR_config[i1]['time_sample'] = {}
    EMULATOR_config[i1]['time_sensor'] = {}
    for i2 in EMULATOR_config['Species_regression']:
        EMULATOR_config[i1]['time_sample'][i2] = time_samples[i2].tolist()

EMULATOR_config['number_br'] = len(mbr_list)
EMULATOR_config['time_execution'] = time_execution
EMULATOR_config['Noise_concentration'] = Noise_concentration
EMULATOR_config['Noise_time'] = Noise_time / 100
EMULATOR_config['acceleration'] = acceleration
EMULATOR_config['experiment_duration'] = t_duration

with open('EMULATOR_config.json', "w") as outfile:
    json.dump(EMULATOR_config, outfile)
