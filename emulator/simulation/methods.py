import numpy as np
import json
from copy import deepcopy
from emulator.simulation.ode import function_simulation


def simulate(time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    NEW_EMULATOR_state = deepcopy(EMULATOR_state)

    nn = 0
    for i1 in EMULATOR_config["Brxtor_list"]:
        ts0 = np.array([time_initial, time_final])
        Xo0 = np.array([EMULATOR_state[i1]["Current"][i2] for i2 in EMULATOR_config["Species_list"]])

        u0 = np.array([EMULATOR_design[i1]["Glucose_feed"], nn, EMULATOR_config["number_br"]])
        THs = EMULATOR_config["Params"]
        D0 = EMULATOR_design[i1]["Profiles"].copy()

        t, y = function_simulation(ts0, Xo0, u0, THs, D0)

        nn2 = 0
        for i2 in EMULATOR_config["Species_list"]:
            NEW_EMULATOR_state[i1]["All"][i2]["time"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["All"][i2]["time"]), t[1:].flatten()
            ).tolist()
            NEW_EMULATOR_state[i1]["All"][i2]["Value"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["All"][i2]["Value"]), y[1:, nn2].flatten()
            ).tolist()
            NEW_EMULATOR_state[i1]["Current"][i2] = float(y[-1, nn2])
            nn2 += 1

        nn += 1

    return NEW_EMULATOR_state


def sample(time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    NEW_EMULATOR_state = deepcopy(EMULATOR_state)

    for i1 in EMULATOR_config["Brxtor_list"]:
        for i2 in EMULATOR_config["Species_regression"]:
            ts_sample_all = np.array(EMULATOR_design[i1]["time_sample"][i2]) * (
                1 + np.random.normal(0, 1, size=len(np.array(EMULATOR_design[i1]["time_sample"][i2])))
                * EMULATOR_config["Noise_time"] * 0
            )

            ts_sample = ts_sample_all[(ts_sample_all > time_initial) & (ts_sample_all <= time_final)]

            tX_state = EMULATOR_state[i1]["All"][i2]["time"]
            X_state = EMULATOR_state[i1]["All"][i2]["Value"]

            X_interp = np.interp(ts_sample, tX_state, X_state)
            X_interp = X_interp * (
                1 + np.random.normal(0, 1, size=len(X_interp)) * EMULATOR_config["Noise_concentration"]
            )

            NEW_EMULATOR_state[i1]["Sample"][i2]["time"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["Sample"][i2]["time"]), ts_sample
            ).tolist()
            NEW_EMULATOR_state[i1]["Sample"][i2]["Value"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["Sample"][i2]["Value"]), X_interp
            ).tolist()

        # Temperature: constant setpoint + noise, same time points as Xv
        temp_setpoint = EMULATOR_config.get("Temperature_setpoint", 37.0)
        temp_noise = EMULATOR_config.get("Noise_temperature", 0.0)

        ts_temp_all = np.array(EMULATOR_design[i1]["time_sample"].get("Xv", []))
        ts_temp = ts_temp_all[(ts_temp_all > time_initial) & (ts_temp_all <= time_final)]

        if len(ts_temp) > 0:
            temp_values = np.full(len(ts_temp), temp_setpoint)
            if temp_noise > 0:
                temp_values = temp_values * (1 + np.random.normal(0, 1, size=len(ts_temp)) * temp_noise)

            NEW_EMULATOR_state[i1]["Sample"]["Temperature"]["time"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["Sample"]["Temperature"]["time"]), ts_temp
            ).tolist()
            NEW_EMULATOR_state[i1]["Sample"]["Temperature"]["Value"] = np.append(
                np.array(NEW_EMULATOR_state[i1]["Sample"]["Temperature"]["Value"]), temp_values
            ).tolist()

    return NEW_EMULATOR_state


def write_measurements(filename, time_initial, time_final, EMULATOR_state, EMULATOR_design, EMULATOR_config):
    with open(filename) as json_file:
        File_dict = json.load(json_file)

    for i1 in EMULATOR_config["Brxtor_list"]:
        for i2 in EMULATOR_config["Species_regression"]:
            ts_new = EMULATOR_state[i1]["Sample"][i2]["time"]
            Xs_new = EMULATOR_state[i1]["Sample"][i2]["Value"]

            File_dict[i1]["measurements_aggregated"][i2]["measurement_time"] = ts_new
            File_dict[i1]["measurements_aggregated"][i2][i2] = Xs_new

        # Temperature
        ts_temp = EMULATOR_state[i1]["Sample"]["Temperature"]["time"]
        temp_vals = EMULATOR_state[i1]["Sample"]["Temperature"]["Value"]
        File_dict[i1]["measurements_aggregated"]["Temperature"]["measurement_time"] = ts_temp
        File_dict[i1]["measurements_aggregated"]["Temperature"]["Temperature"] = temp_vals

        ts_pulse_new = np.array(EMULATOR_design[i1]["Profiles"]["time_feed"])
        F_pulse_new = np.array(EMULATOR_design[i1]["Profiles"]["Feed_profile"])

        F_pulse_new = F_pulse_new[ts_pulse_new < time_final]
        ts_pulse_new = ts_pulse_new[ts_pulse_new < time_final]

        File_dict[i1]["measurements_aggregated"]["Feed_meas"]["measurement_time"] = ts_pulse_new.tolist()
        File_dict[i1]["measurements_aggregated"]["Feed_meas"]["Feed_meas"] = F_pulse_new.tolist()

    with open(filename, "w") as outfile:
        json.dump(File_dict, outfile)

    return File_dict
