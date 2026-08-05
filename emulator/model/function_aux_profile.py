import numpy as np
import yaml


def yaml_to_profile(profile_name='profile_initial_template.yaml', time_current=0, pioreactor_list=['pio01', 'worker01']):
    """
    Read a YAML profile and return a dict with 'time_feed' and 'Feed_profile' for each pioreactor.
    """
    with open(profile_name, 'r') as file:
        profile_yaml = yaml.safe_load(file)

    Pulse_profile_dict = {}
    for i1 in pioreactor_list:
        Pulse_profile_dict[i1] = {'time_feed': [], 'Feed_profile': []}

    for i1 in pioreactor_list:
        for i2 in profile_yaml['pioreactors'][i1]['jobs']['add_media']['actions']:
            time_pulse_i = float(i2['t'])
            feed_pulse_i = float(i2['options']['ml'])

            Pulse_profile_dict[i1]['time_feed'] = Pulse_profile_dict[i1]['time_feed'] + [time_pulse_i + time_current]
            Pulse_profile_dict[i1]['Feed_profile'] = Pulse_profile_dict[i1]['Feed_profile'] + [feed_pulse_i]

    return Pulse_profile_dict


def profile_to_yaml(time_current, feed_dict, profile_name='profile_add_template.yaml', pioreactor_list=['pio01', 'worker01']):
    """
    Convert a feed dict (with 'time_feed' and 'Feed_profile' per pioreactor) into a YAML-compatible dict.
    """
    with open(profile_name, 'r') as file:
        profile_yaml = yaml.safe_load(file)

    for i1 in pioreactor_list:
        time_pulse_0 = np.array(feed_dict[i1]['time_feed'])
        time_pulse_new = time_pulse_0[time_pulse_0 > time_current]
        feed_pulse_0 = np.array(feed_dict[i1]['Feed_profile'])
        feed_pulse_new = feed_pulse_0[time_pulse_0 > time_current]

        profile_yaml['pioreactors'][i1]['jobs']['add_media']['actions'] = []
        profile_yaml['pioreactors'][i1]['jobs']['remove_waste']['actions'] = []

        for t1, d1 in zip(time_pulse_new.tolist(), feed_pulse_new.tolist()):
            profile_yaml['pioreactors'][i1]['jobs']['add_media']['actions'].append({
                'type': 'start',
                't': t1 - time_current,
                'options': {'ml': d1},
            })
            profile_yaml['pioreactors'][i1]['jobs']['remove_waste']['actions'].append({
                'type': 'start',
                't': t1 - time_current + 0.0003,
                'options': {'ml': d1 * 2},
            })

    return profile_yaml


if __name__ == "__main__":
    time_pulse = np.array([2, 3, 5, 10]) / 60
    feed_pulse = time_pulse * 0 + 0.5

    Feed_dict = {'pio01': {}, 'worker01': {}}
    for i1 in ['pio01', 'worker01']:
        Feed_dict[i1] = {'time_feed': time_pulse.tolist(), 'Feed_profile': feed_pulse.tolist()}

    prof_dict = profile_to_yaml(0, Feed_dict, profile_name='profile_add_template.yaml', pioreactor_list=['pio01', 'worker01'])

    with open('profile_test2.yaml', 'w') as file:
        yaml.dump(prof_dict, file, sort_keys=False, default_flow_style=False)
