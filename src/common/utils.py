import os
from src.common import constants
import pandas as pd


def create_folder(folder_key):
    """
    create_folder function is used to take the folder key
    @param:
        folder_key = path to create folder with folder name e.g.:/tmp/sample_output/
    """
    # create a output folder if not exist
    if not os.path.exists(folder_key):
        os.makedirs(folder_key)

def output_file_restructure(output_path):
    scenario_path_lst = [x[0] for x in os.walk(output_path)][1::]
    for file_name, new_file_name in constants.output_files.items():
        appended_file = []
        for scenario_pa in scenario_path_lst:
            path = str(os.path.join(scenario_pa,file_name))
            try:
                df = pd.read_csv(path)
            except:
                df = pd.DataFrame()
            df['scenario_name'] = os.path.basename(os.path.normpath(scenario_pa))
            appended_file.append(df)
        combined = pd.concat(appended_file, ignore_index=True)
        combined.to_csv(os.path.join(str(output_path),new_file_name), index=False)

def clear_model(model):
    # OR-Tools shim: recreate the underlying SCIP solver from scratch
    if hasattr(model, '_reset'):
        model._reset()
        return model
    # Gurobi path: remove all constraints, variables, and reset objective
    model.remove(model.getGenConstrs())
    model.remove(model.getConstrs())
    model.remove(model.getVars())
    model.remove(model.getQConstrs())
    model.remove(model.getSOSs())
    model.setObjective(0.0)
    model.NumObj = 0
    model.update()
    return model


def find_valid_period(start, end, period_day_name_mapping, dc_slot_schedule_dict):
    for period in range(start, end + 1):
        day_name = period_day_name_mapping[period]['day_name']
        if dc_slot_schedule_dict.get(day_name, 0) > 0:
            return period
    return None