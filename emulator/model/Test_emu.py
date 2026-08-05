"""Test script for running the emulator in single-step or stepwise mode."""

import json
import time
import numpy as np
import matplotlib.pyplot as plt

import Node_start_emulator
import Node_run_emulator


def main():
    with open('EMULATOR_config.json') as f:
        config = json.load(f)

    acceleration = config['acceleration']
    exp_duration = config['experiment_duration']

    Node_start_emulator.start_EXP()

    if acceleration == 54000:
        # Single step: run the entire experiment at once
        time.sleep(1.4)
        Node_run_emulator.run_emu()
    else:
        # Stepwise: simulate every 60 real-seconds until experiment_duration is reached
        step_interval = 60  # seconds of wall clock per step

        while True:
            time.sleep(step_interval)
            Node_run_emulator.run_emu()

            with open('EMULATOR_state.json') as f:
                state = json.load(f)
            elapsed = state['time']
            print(f'Simulated time: {elapsed:.2f} h / {exp_duration:.2f} h')

            if elapsed >= exp_duration:
                break




if __name__ == '__main__':
    main()
