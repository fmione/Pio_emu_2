"""Plot emulator simulation results and database measurements."""

import numpy as np
import json
import matplotlib.pyplot as plt

with open('EMULATOR_state.json') as json_file:
    EMULATOR_state = json.load(json_file)
with open('db_emulator.json') as json_file:
    db_emulator = json.load(json_file)

i1 = 'pio01'

tp = np.array(db_emulator[i1]['measurements_aggregated']['Feed_meas']['measurement_time'])
fp = np.array(db_emulator[i1]['measurements_aggregated']['Feed_meas']['Feed_meas'])

tsx = np.array(db_emulator[i1]['measurements_aggregated']['Xv']['measurement_time'])
xs = np.array(db_emulator[i1]['measurements_aggregated']['Xv']['Xv'])

tss = np.array(db_emulator[i1]['measurements_aggregated']['Glucose']['measurement_time'])
ss = np.array(db_emulator[i1]['measurements_aggregated']['Glucose']['Glucose'])

plt.plot( tsx , xs, '.', tss , ss, '.')
plt.show()
