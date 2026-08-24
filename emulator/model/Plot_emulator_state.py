"""Plot emulator simulation results and database measurements."""

import numpy as np
import json
import matplotlib.pyplot as plt

def plot_results():
    with open('EMULATOR_state.json') as json_file:
        EMULATOR_state = json.load(json_file)
    with open('EMULATOR_config.json') as json_file:
        EMULATOR_config = json.load(json_file)
    with open('db_emulator.json') as json_file:
        db_emulator = json.load(json_file)
    
    mbr_list=[ 'pio01', 'worker01']
    species_list=['Xv','Glucose']
    
    fig, axes = plt.subplots(1, len(mbr_list))
    
    
    for n1,i1 in enumerate(mbr_list):
        ax = axes[n1]
        tp = np.array(db_emulator[i1]['measurements_aggregated']['Feed_meas']['measurement_time'])
        fp = np.array(db_emulator[i1]['measurements_aggregated']['Feed_meas']['Feed_meas'])
        ax.plot(tp , fp, '*')
        # ax.legend('pulse')
        for i2 in species_list:
            
            tt = np.array(EMULATOR_state[i1]['All'][i2]['time'])
            xx = np.array(EMULATOR_state[i1]['All'][i2]['Value'])
            
            if i2 == 'Xv':
                tsx = np.array(db_emulator[i1]['measurements_aggregated']['OD']['measurement_time'])
                xs = np.array(db_emulator[i1]['measurements_aggregated']['OD']['OD'])/EMULATOR_config['OD_factor'][i1]
            else:
                tsx = np.array(db_emulator[i1]['measurements_aggregated'][i2]['measurement_time'])
                xs = np.array(db_emulator[i1]['measurements_aggregated'][i2][i2])
            ax.plot(tsx , xs, '.',tt , xx)
            # ax.legend(i2)
                
        ax.set_xlabel('time (min)')
        ax.set_ylabel('Concentration [g/l]')
        ax.set_title(f'{i1}')
        # ax.legend(fontsize=7)
        ax.grid(True)
    
if __name__ == "__main__":
    plot_results()

