import paramiko
import json
import os
from datetime import datetime, timedelta


def connect_ssh():
    """
    Establishes an SSH connection to the local pioreactor host (Docker container).
    """

    hostname = os.environ.get("SSH_LOCAL_HOST")
    username = os.environ.get("SSH_USERNAME")
    password = os.environ.get("SSH_PASSWORD")
    db_path = os.environ.get("PIO_DB_PATH")


    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(
        hostname=hostname,
        username=username,
        password=password,
        timeout=10
    )

    return client, db_path


def get_config():    
    """
    Retrieves the experiment configuration.
    """

    with open(f"EMULATOR_config.json") as json_file:   
        emulator_config = json.load(json_file)

    return emulator_config["exp_name"], emulator_config["Brxtor_list"], emulator_config["OD_factor"]


def init():
    """
    Initializes the pioreactor database by adding workers, an experiment entry and the corresponding assignments.
    """

    start_datetime = datetime.now().replace(microsecond=0).isoformat()
    
    # for XCom in Airflow
    print(start_datetime)

    client, db_path = connect_ssh()
    exp_name, mbr_list, _ = get_config()

    workers_sql = f"""INSERT OR IGNORE INTO workers (pioreactor_unit, added_at, is_active)
     VALUES {", ".join(f"('{unit}', '{start_datetime}', 1)" for unit in mbr_list)};"""  
    
    experiment_sql = f"""INSERT INTO experiments (experiment, created_at)
     VALUES ('{exp_name}', '{start_datetime}');"""

    assignments_sql = f"""INSERT INTO experiment_worker_assignments_history (pioreactor_unit, experiment, assigned_at)
     VALUES {", ".join(f"('{unit}', '{exp_name}', '{start_datetime}')" for unit in mbr_list)};"""


    _, _, stderr = client.exec_command(f"""
sqlite3 {db_path} <<'EOF'
.bail on
BEGIN;
{workers_sql}
{experiment_sql}
{assignments_sql}
COMMIT;
EOF""")

    error = stderr.read().decode().strip()
    if error:
        raise RuntimeError(f"SQLite error:\n{error}")
    
    client.close()
    

def clean_db():
    """
    Deletes all entries related to the current experiment from the pioreactor database.
    """

    client, db_path = connect_ssh()
    exp_name, _, _ = get_config()
    
    experiment_sql = f"""DELETE FROM experiments WHERE experiment = '{exp_name}';"""
    assignments_sql = f"""DELETE FROM experiment_worker_assignments_history WHERE experiment = '{exp_name}';"""
    od_readings_sql = f"""DELETE FROM od_readings WHERE experiment = '{exp_name}';"""
    dosing_sql = f"""DELETE FROM dosing_events WHERE experiment = '{exp_name}';"""

    _, _, stderr = client.exec_command(f"""
sqlite3 {db_path} <<'EOF'
.bail on
BEGIN;
{dosing_sql}
{od_readings_sql}
{assignments_sql}
{experiment_sql}
COMMIT;
EOF""")

    error = stderr.read().decode().strip()
    if error:
        raise RuntimeError(f"SQLite error:\n{error}")
    
    client.close()


def save_measurements(start_datetime):
    """
    Saves OD readings and dosing events in the pioreactor database.
    """
    
    exp_name, mbr_list, OD_factor = get_config()
    with open("db_emulator.json") as json_file:   
        db_emulator = json.load(json_file)

    # OD readings        
    values_list = []
    for unit in mbr_list:
        t_od=db_emulator[unit]["measurements_aggregated"]["Xv"]["measurement_time"]
        m_od=[x * OD_factor[unit] for x in db_emulator[unit]["measurements_aggregated"]["Xv"]["Xv"]]
        
        values_list.extend(
            f"('{exp_name}', '{unit}', '{(datetime.fromisoformat(start_datetime) + timedelta(hours=ti)).isoformat()}', {od}, 90, 2)"
            for ti, od in list(zip(t_od, m_od))
        )
    
    
    
    if len(values_list) == 0:
        return  
    else:
        values = ", ".join(values_list)
    
    od_readings_sql = f"""INSERT OR IGNORE INTO od_readings
        (experiment, pioreactor_unit, timestamp, od_reading, angle, channel) VALUES {values};"""
    

    
    client, db_path = connect_ssh()
    stdin, _, _ = client.exec_command(f"cat > /tmp/od_readings.sql")
    stdin.write(od_readings_sql)
    stdin.close()

    _, _, stderr = client.exec_command(f"sqlite3 {db_path} < /tmp/od_readings.sql")

    error = stderr.read().decode().strip()
    if error:
        raise RuntimeError(f"SQLite error:\n{error}")
    
    client.close()


    # dosing events
    values_list = []
    for unit in mbr_list:
        # take current time from Xv measurement
        current_time = db_emulator[unit]["measurements_aggregated"]["Xv"]["measurement_time"][-1]

        t_dosing=db_emulator[unit]["measurements_aggregated"]["Feed_meas"]["measurement_time"]
        m_dosing=db_emulator[unit]["measurements_aggregated"]["Feed_meas"]["Feed_meas"]
        
        for ti, di in list(zip(t_dosing, m_dosing)):
            if ti <= current_time:
                values_list.extend([f"('{exp_name}', '{unit}', '{(datetime.fromisoformat(start_datetime) + timedelta(hours=ti)).isoformat()}', 'add_media', {di})"])
    
    if len(values_list) == 0:
        return  
    else:
        values = ", ".join(values_list)
    
    dosing_events_sql = f"""INSERT OR IGNORE INTO dosing_events
        (experiment, pioreactor_unit, timestamp, event, volume_change_ml) VALUES {values};"""
    
    client, db_path = connect_ssh()
    stdin, _, _ = client.exec_command(f"cat > /tmp/dosing_events.sql")
    stdin.write(dosing_events_sql)
    stdin.close()

    _, _, stderr = client.exec_command(f"sqlite3 {db_path} < /tmp/dosing_events.sql")

    error = stderr.read().decode().strip()
    if error:
        raise RuntimeError(f"SQLite error:\n{error}")
    
    client.close()

def clean_profile_folder():
   """ 
   Removes all YAML files in the pioreactor container
   """

   client, _ = connect_ssh()

   exp_profile_path = f"/home/pioreactor/.pioreactor/experiment_profiles/*"
   _, stdout, _ = client.exec_command(f'rm -f {exp_profile_path}')
   stdout.channel.recv_exit_status()

   client.close() 


def get_yaml_updated(filename="profile_update.yaml"):
   """ 
   Gets current YAML file from the pioreactor container
   """

   client, _ = connect_ssh()

   try:
       exp_profile_path = f"/home/pioreactor/.pioreactor/experiment_profiles/{filename}"
       
       sftp = client.open_sftp()
       sftp.stat(exp_profile_path)
       sftp.get(exp_profile_path, filename)
       sftp.close()
   except:
       print('Missing file')

   client.close() 