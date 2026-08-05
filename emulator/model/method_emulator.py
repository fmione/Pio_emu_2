import numpy as np
import json
from copy import deepcopy
import pandas as pd
from function_simulation import function_simulation


def simulate(time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    """Run the ODE simulation for all bioreactors over [time_initial, time_final]."""
    NEW_EMULATOR_state = deepcopy(EMULATOR_state)

    nn = 0
    for i1 in EMULATOR_config['Brxtor_list']:
        ts0 = np.array([time_initial, time_final])
        Xo0 = np.array([])
        for i2 in EMULATOR_config['Species_list']:
            Xo0 = np.append(Xo0, EMULATOR_state[i1]['Current'][i2])

        u0 = np.array([EMULATOR_design[i1]['Glucose_feed'], nn, EMULATOR_config['number_br']])

        THs = EMULATOR_config['Params']
        D0 = EMULATOR_design[i1]['Profiles'].copy()

        t, y = function_simulation(ts0, Xo0, u0, THs, D0)

        nn2 = 0
        for i2 in EMULATOR_config['Species_list']:
            NEW_EMULATOR_state[i1]['All'][i2]['time'] =  t[1:].flatten().tolist()
            NEW_EMULATOR_state[i1]['All'][i2]['Value'] = y[1:, nn2].flatten().tolist()
            NEW_EMULATOR_state[i1]['Current'][i2] = float(y[-1, nn2])
            nn2 = nn2 + 1

        nn = nn + 1

    return NEW_EMULATOR_state


def sample(time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    """Generate noisy measurements from the simulated trajectory."""
    NEW_EMULATOR_state = deepcopy(EMULATOR_state)

    for i1 in EMULATOR_config['Brxtor_list']:
        for i2 in EMULATOR_config['Species_regression']:
            ts_sample_all = np.array(EMULATOR_design[i1]['time_sample'][i2]) * (
                1 + np.random.normal(0, 1, size=len(np.array(EMULATOR_design[i1]['time_sample'][i2]))) * EMULATOR_config['Noise_time'] * 0
            )

            ts_sample = ts_sample_all[(ts_sample_all > time_initial) & (ts_sample_all <= time_final)]

            tX_state = EMULATOR_state[i1]['All'][i2]['time']
            X_state = EMULATOR_state[i1]['All'][i2]['Value']

            X_interp = np.interp(ts_sample, tX_state, X_state)
            X_interp = X_interp * (1 + np.random.normal(0, 1, size=len(X_interp)) * EMULATOR_config['Noise_concentration'])

            NEW_EMULATOR_state[i1]['Sample'][i2]['time'] = np.append(
                np.array(NEW_EMULATOR_state[i1]['Sample'][i2]['time']), ts_sample
            ).tolist()
            NEW_EMULATOR_state[i1]['Sample'][i2]['Value'] = np.append(
                np.array(NEW_EMULATOR_state[i1]['Sample'][i2]['Value']), X_interp
            ).tolist()

    return NEW_EMULATOR_state


def write(filename, time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    """Write measurements and feed profiles to the emulator database JSON file."""
    with open(filename) as json_file:
        File_dict = json.load(json_file)

    for i1 in EMULATOR_config['Brxtor_list']:
        for i2 in EMULATOR_config['Species_regression']:
            ts_new = EMULATOR_state[i1]['Sample'][i2]['time']
            Xs_new = EMULATOR_state[i1]['Sample'][i2]['Value']

            File_dict[i1]['measurements_aggregated'][i2]['measurement_time'] = ts_new
            File_dict[i1]['measurements_aggregated'][i2][i2] = Xs_new

        ts_pulse_new = np.array(EMULATOR_design[i1]['Profiles']['time_feed'])
        F_pulse_new = np.array(EMULATOR_design[i1]['Profiles']['Feed_profile'])

        F_pulse_new = F_pulse_new[ts_pulse_new < time_final]
        ts_pulse_new = ts_pulse_new[ts_pulse_new < time_final]

        File_dict[i1]['measurements_aggregated']['Feed_meas']['measurement_time'] = ts_pulse_new.tolist()
        File_dict[i1]['measurements_aggregated']['Feed_meas']['Feed_meas'] = F_pulse_new.tolist()

    with open(filename, "w") as outfile:
        json.dump(File_dict, outfile)

    return File_dict


def read(time_initial, filename, EMULATOR_design, EMULATOR_config):
    """Read feed profiles from the database and append any new pulses beyond the last recorded time."""
    NEW_EMULATOR_design = deepcopy(EMULATOR_design)

    with open(filename) as json_file:
        File_dict_db = json.load(json_file)

    for i1 in EMULATOR_config['Brxtor_list']:
        tp = np.array(File_dict_db[i1]['measurements_aggregated']['Feed_meas']['measurement_time'])
        fp = np.array(File_dict_db[i1]['measurements_aggregated']['Feed_meas']['Feed_meas'])

        if len(tp) == 0:
            tp = np.array(EMULATOR_design[i1]['Profiles']['time_feed'])
            fp = np.array(EMULATOR_design[i1]['Profiles']['Feed_profile'])

        new_time_feeds = np.array(EMULATOR_design[i1]['Profiles']['time_feed'])
        new_Feed_profiles = np.array(EMULATOR_design[i1]['Profiles']['Feed_profile'])
        new_Feed_profiles = (new_Feed_profiles[(new_time_feeds > tp[-1]) & (new_time_feeds >= time_initial)]).tolist()
        new_time_feeds = (new_time_feeds[(new_time_feeds > tp[-1]) & (new_time_feeds >= time_initial)]).tolist()

        NEW_EMULATOR_design[i1]['Profiles']['time_feed'] = tp.tolist() + new_time_feeds
        NEW_EMULATOR_design[i1]['Profiles']['Feed_profile'] = fp.tolist() + new_Feed_profiles
        print('current:', time_initial, i1, 'Profiles', NEW_EMULATOR_design[i1]['Profiles']['time_feed'])

    return NEW_EMULATOR_design

def write_csv(filename_csv, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    """Write atline measurements to a csv file."""

    time_start_absolute = EMULATOR_design['time_start_absolute']
    
    csv_data={}
    for i1 in EMULATOR_config['Brxtor_list']:
        csv_data[i1]=pd.DataFrame({'t':EMULATOR_state[i1]['Sample']['Glucose']['time'],f'glucose_{i1}':EMULATOR_state[i1]['Sample']['Glucose']['Value']}).set_index('t')

    df_csv = pd.concat([csv_data[i1] for i1 in EMULATOR_config['Brxtor_list']], axis=1).reset_index()
    
    df_csv["t"]=df_csv["t"]*3600+time_start_absolute
    df_csv = df_csv.sort_values("t").reset_index(drop=True)
    df_csv["t"] = pd.to_datetime(df_csv["t"], unit="s", utc=True).dt.tz_convert("Etc/GMT+3").dt.strftime("%H:%M:%S")
    df_csv.to_csv(filename_csv, sep=";", index=False)
    return 