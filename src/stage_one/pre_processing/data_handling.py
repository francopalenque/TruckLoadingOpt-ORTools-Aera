import sys
from src.common.logger_config import logger
from src.common import constants
import os
import pandas as pd
import isodate
from datetime import datetime, timedelta
import math
import numpy as np
import itertools
from src.common.utils import find_valid_period


def fix_column_names(df):
    df.columns = [name.lower().strip('_').replace(" ", "_") for name in df.columns]
    if 'non_available_order_flag' in df.columns:
        df = df.rename(columns={'non_available_order_flag': 'non-available_order_flag'})
    return df

def get_string_columns_mapping(table_name):
    string_columns = {}
    if table_name in constants.data_column_mapping:
        for col_key, col_val in constants.data_column_mapping[table_name].items():
            if col_val['type'] == 'string':
                string_columns[col_key] = col_val['type']
    return string_columns

def remove_files_in_folder(path,file_type):
    for filename in os.listdir(path):
        if filename.endswith(file_type):
            rmv_file_path = os.path.join(path, filename)
            os.remove(rmv_file_path)


def create_data_dictionary(upload_type, input_path):
    input_tables_dict = {}
    if upload_type == "bulk_upload":
        required_file = constants.required_bulk_upload_file[0]
        if os.path.exists(os.path.join(input_path, required_file)):
            input_tables = pd.ExcelFile(os.path.join(input_path, required_file))
            input_sheets = input_tables.sheet_names
            updated_input_sheets = [sheet_name.lower().replace(" ", "_") for sheet_name in input_sheets]
            for i in range(len(input_sheets)):
                input_tables_dict[updated_input_sheets[i]] = fix_column_names(input_tables.parse(input_sheets[i]))
    else:
        required_file = constants.data_column_mapping.keys()
        for file in required_file:
            file_format = constants.file_format
            file_name = "{}.{}".format(file, file_format)
            updated_file_name = file_name.split('.')[0].lower().replace(" ", "_")
            if os.path.exists(os.path.join(input_path, file_name)):
                try:
                    if file_format == 'csv':
                        string_columns = get_string_columns_mapping(file)
                        if len(string_columns) > 0:
                            df = pd.read_csv(os.path.join(input_path, file_name),dtype=string_columns)
                        else:
                            df = pd.read_csv(os.path.join(input_path, file_name))
                        input_tables_dict[updated_file_name] = fix_column_names(df)
                    elif file_format == 'xlsx':
                        input_tables_dict[updated_file_name] = fix_column_names(pd.read_excel(os.path.join(input_path, file_name)))
                except:
                    column_names = constants.data_column_mapping[updated_file_name].keys()
                    column_names = [name.lower().replace(" ", "_") for name in column_names]
                    input_tables_dict[updated_file_name] = pd.DataFrame(columns=column_names)
            else:
                column_names = constants.data_column_mapping[updated_file_name].keys()
                column_names = [name.lower().replace(" ", "_") for name in column_names]
                input_tables_dict[updated_file_name] = pd.DataFrame(columns=column_names)

    return input_tables_dict


def transform_date(input_tables_dict):
    for key, df in input_tables_dict.items():
        if key in constants.date_transformation:
            for column in constants.date_transformation[key]:
                df[column] = df[column].replace('0001-01-01', pd.NaT)
                flag = False
                for i in ['%d/%m/%y', '%d-%b-%y']:
                    try:
                        df[column] = pd.to_datetime(df[column],format=i)
                        flag = True
                        break
                    except Exception:
                        logger.info(f'The format of: {key} table - {column} column is not matching with {i}')
                if not flag:
                    try:
                        df[column] = pd.to_datetime(df[column])
                    except Exception as e:
                        logger.info(f'Date format issue {e}')
                df[column] = df[column].dt.strftime(constants.date_format)
            input_tables_dict[key] = df
    return input_tables_dict

def get_dc_list(input_tables_dict):
    general_configurations = input_tables_dict['general_configurations']

    start_date = pd.to_datetime(general_configurations['start_date'][0]).date()
    end_date = pd.to_datetime(general_configurations['end_date'][0]).date()
    start_date = start_date.strftime('%Y-%m-%d')
    end_date = end_date.strftime('%Y-%m-%d')

    apo_truck_load_df = input_tables_dict['apo_truck_load']

    apo_truck_load_df["requested_delivery_date"] = pd.to_datetime(apo_truck_load_df["requested_delivery_date"],format=constants.date_format)
    # Create new column with week day names
    apo_truck_load_df['requested_delivery_day_name'] = apo_truck_load_df["requested_delivery_date"].dt.day_name()
    apo_truck_load_df["requested_delivery_date"] = apo_truck_load_df["requested_delivery_date"].dt.strftime(constants.date_format)
    apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["requested_delivery_date"] >= start_date]
    apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["requested_delivery_date"] <= end_date]

    apo_truck_load_df["delivery_date"] = pd.to_datetime(apo_truck_load_df["delivery_date"],format=constants.date_format)
    apo_truck_load_df['delivery_day_name'] = apo_truck_load_df["delivery_date"].dt.day_name()
    apo_truck_load_df["delivery_date"] = apo_truck_load_df["delivery_date"].dt.strftime(constants.date_format)
    apo_truck_load_df["original_delivery_date"] = apo_truck_load_df["delivery_date"]
    apo_truck_load_df["delivery_date"] = np.where(apo_truck_load_df["delivery_date"] < start_date,start_date, apo_truck_load_df["delivery_date"])
    input_tables_dict['original_apo_truck_load'] = apo_truck_load_df
    # do not filter on delivery date end date- this will miss pushing them in leftover truck - anjali K, 5/19/26
    # apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["delivery_date"] <= end_date]
    input_tables_dict['apo_truck_load'] = apo_truck_load_df

    return apo_truck_load_df['dc'].unique().tolist(), input_tables_dict


def filter_dataframe(input_tables_dict, dc):
    dc_input_tables_dict = dict()
    dc_input_tables_dict['general_configurations'] = input_tables_dict['general_configurations']

    start_date = pd.to_datetime(input_tables_dict['general_configurations']['start_date'][0]).date()
    end_date = pd.to_datetime(input_tables_dict['general_configurations']['end_date'][0]).date()
    start_date = start_date.strftime('%Y-%m-%d')
    end_date = end_date.strftime('%Y-%m-%d')

    dc_input_tables_dict['dc_slot_schedule'] = input_tables_dict['dc_slot_schedule'][input_tables_dict['dc_slot_schedule']['dc'] == dc].copy().reset_index(drop=True)
    # Filter on truck capacity details
    temp_truck_capacity_details = input_tables_dict['truck_capacity_details'][input_tables_dict['truck_capacity_details']['dc'] == dc].copy()
    temp_truck_capacity_details["requested_delivery_date"] = pd.to_datetime(temp_truck_capacity_details["requested_delivery_date"], format=constants.date_format)
    # Create new column with week day names
    temp_truck_capacity_details['requested_delivery_day_name'] = temp_truck_capacity_details["requested_delivery_date"].dt.day_name()
    temp_truck_capacity_details["requested_delivery_date"] = temp_truck_capacity_details["requested_delivery_date"].dt.strftime(constants.date_format)
    temp_truck_capacity_details = temp_truck_capacity_details.loc[temp_truck_capacity_details["requested_delivery_date"] >= start_date]
    temp_truck_capacity_details = temp_truck_capacity_details.loc[temp_truck_capacity_details["requested_delivery_date"] <= end_date]
    actual_truck_count = len(temp_truck_capacity_details)
    # Left Over Truck
    dc_input_tables_dict['left_over_truck_capacity_details'] = temp_truck_capacity_details[temp_truck_capacity_details['leftover_truck_flag'] == 'Y'].copy()
    print(len(dc_input_tables_dict['left_over_truck_capacity_details']))
    print("**"*10)
    temp_truck_capacity_details = temp_truck_capacity_details[temp_truck_capacity_details['leftover_truck_flag'] == 'N'].copy()
    temp_truck_capacity_details['po_utilization'] = temp_truck_capacity_details[["po_utilization_weight", "po_utilization_volume", "po_utilization_pallet"]].max(axis=1)
    temp_truck_details_under_utilized = pd.DataFrame(columns=temp_truck_capacity_details.columns) # temp_truck_capacity_details[temp_truck_capacity_details['po_utilization'] < 100]
    temp_truck_details_fully_utilized = pd.DataFrame(columns=temp_truck_capacity_details.columns) # temp_truck_capacity_details[temp_truck_capacity_details['po_utilization'] >= 100]
    # ALL trucks go to optimizer (no utilization threshold filter)
    dc_input_tables_dict['truck_capacity_details'] = temp_truck_capacity_details

    # Filter on apo truck load — ALL order lines go to optimizer
    temp_apo_truck_load = input_tables_dict['apo_truck_load'][(input_tables_dict['apo_truck_load']['dc'] == dc)].copy()
    # Left Over Truck
    dc_input_tables_dict['left_over_apo_truck_load'] = temp_apo_truck_load[temp_apo_truck_load['non-available_order_flag'] == 'Y'].copy()
    temp_apo_truck_load = temp_apo_truck_load[(temp_apo_truck_load['confirmed_quantity_in_base_unit'] > 0)].copy()
    temp_apo_truck_load = temp_apo_truck_load[temp_apo_truck_load['non-available_order_flag'] == 'N'].copy()
    temp_apo_truck_load_fully_utilized = pd.DataFrame(columns=temp_apo_truck_load.columns) # temp_apo_truck_load[temp_apo_truck_load['po_number'].isin(temp_truck_details_fully_utilized['po_number'].unique()) == True]
    temp_apo_truck_load_under_utilized = pd.DataFrame(columns=temp_apo_truck_load.columns) # temp_apo_truck_load[temp_apo_truck_load['po_number'].isin(temp_truck_details_fully_utilized['po_number'].unique()) == False]
    dc_input_tables_dict['apo_truck_load'] = temp_apo_truck_load
    return dc_input_tables_dict, temp_apo_truck_load_fully_utilized, temp_truck_details_fully_utilized, actual_truck_count

def reduce_slots_for_leftover_truck(df, horizon, period_day_name_mapping):

    start_period = 1
    end_period = horizon

    garbage_truck_period = None
    current_period = end_period
    while current_period >= start_period:
        # get weekday name
        day_name = period_day_name_mapping[current_period]['day_name']
        # find matching row
        idx = df[df["week_name"] == day_name].index
        if len(idx) > 0:
            idx = idx[0]
            # check value
            if df.at[idx, "number_of_slots"] > 0:
                # reduce by 1
                df.at[idx, "number_of_slots"] -= 1
                garbage_truck_period = current_period
                logger.info(f"Reduced 1 from {day_name}")
                break
        # move one day back
        current_period -= 1
    return df, garbage_truck_period



class DataHandling:
    def __init__(self, project_id, plan_id, input_tables_dict, input_path, truck_details_fully_utilized):
        self.project_id = project_id
        self.plan_id = plan_id
        self.input_tables_dict = input_tables_dict
        self.input_path = input_path
        self.truck_details_fully_utilized = truck_details_fully_utilized

        self.model_parameters = None
        self.horizon, self.date_to_period, self.period_to_date = None, None, None
        self.precision_in_days = None
        self.period_day_name_mapping = None
        self.apo_truck_load_dict = None
        self.truck_capacities, self.truck_po_level_details = None, None
        self.dc_slot_schedule_dict = None
        (self.order_allocation_combinations, self.truck_selection_combinations, self.order_truck_mapping, self.period_truck_mapping,
         self.truck_period_mapping, self.original_truck_order_mapping, self.order_selection_mapping_dict, self.shuffle_together_mapping_dict, self.shuffle_order_schedule_line_mapping_dict, self.order_with_no_slots) = None, None, None, None, None, None, None, None, None, None
        self.apo_truck_load_df, self.truck_capacity_details_df = None, None
        self.garbage_truck_po_number, self.garbage_truck_period = None, None

    def prepare_model_data(self):
        self.model_parameters = self.read_global_parameters()
        self.horizon, self.date_to_period, self.period_to_date = self.get_periods_from_dates()
        self.precision_in_days = self.get_days_from_time_string(constants.bucket)
        self.period_day_name_mapping = self.get_day_name_from_period_dates()
        self.apo_truck_load_dict = self.read_apo_truck_load()
        self.truck_capacities, self.truck_po_level_details = self.read_truck_capacity_details()
        self.dc_slot_schedule_dict = self.read_dc_slot_schedule()
        (self.order_allocation_combinations, self.truck_selection_combinations, self.order_truck_mapping, self.period_truck_mapping,
         self.truck_period_mapping, self.original_truck_order_mapping, self.order_selection_mapping_dict, self.shuffle_together_mapping_dict, self.shuffle_order_schedule_line_mapping_dict, self.order_with_no_slots) = self.create_apo_truck_load_combinations()


    @staticmethod
    def get_days_from_time_string(iso_time_string):

        time_object = isodate.parse_duration(iso_time_string)

        return time_object.total_seconds() / 86400

    @staticmethod
    def get_periods_from_days(lead_time_in_days, precision_in_days):

        return math.floor(lead_time_in_days / precision_in_days)

    def get_periods_from_dates(self):
        start_date = isodate.parse_date(self.model_parameters['start_date'])
        end_date = isodate.parse_date(self.model_parameters['end_date'])
        precision = isodate.parse_duration(self.model_parameters['precision'])
        date_format_split_list = self.model_parameters['start_date'].split(constants.ISO_FORMAT_SEPARATOR)
        ISO_FORMAT = constants.ISO_FORMAT_SEPARATOR + date_format_split_list[1] if len(date_format_split_list) > 1 else ""

        date_to_period = {str(start_date) + ISO_FORMAT: 1}
        period_to_date = {1: str(start_date) + ISO_FORMAT}
        period = 1
        current_date = start_date

        while True:
            current_date += precision
            if end_date < current_date:
                break

            period += 1
            date_to_period[str(current_date) + ISO_FORMAT] = period
            period_to_date[period] = str(current_date) + ISO_FORMAT

        horizon = len(date_to_period)

        return horizon, date_to_period, period_to_date

    def get_day_name_from_period_dates(self):
        data = pd.DataFrame(list(self.date_to_period.items()), columns=['date', 'period'])
        data['date'] = pd.to_datetime(data['date'])
        data['day'] = data['date'].dt.day_name()
        data["date"] = data["date"].dt.strftime(constants.date_format)

        period_day_name_mapping = {}
        for index, row in data.iterrows():
            period_day_name_mapping[row['period']] = {'date': row['date'], 'day_name': row['day']}
        return period_day_name_mapping

    def read_global_parameters(self):
        global_parameters_df = self.input_tables_dict['general_configurations']

        global_parameters_dict = {}
        for index, row in global_parameters_df.iterrows():
            global_parameters_dict['end_date'] =  row['end_date']
            global_parameters_dict['run_date'] = row['run_date']
            global_parameters_dict['start_date'] = row['start_date']

        start_date = pd.to_datetime(global_parameters_dict['start_date']).date()
        end_date = pd.to_datetime(global_parameters_dict['end_date']).date()
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')
        precision = constants.bucket
        mip_gap = 0.0001

        model_parameters = {
            "start_date": start_date,
            "end_date": end_date,
            "precision": precision,
            "MIP_GAP": mip_gap,
            "max_trucks_per_order_item": 2,
        }
        logger.info("Model Parameter Dict Created")
        return model_parameters

    def read_apo_truck_load(self):
        apo_truck_load_df = self.input_tables_dict['apo_truck_load']

        apo_truck_load_df["requested_delivery_date"] = pd.to_datetime(apo_truck_load_df["requested_delivery_date"],format=constants.date_format)
        # Create new column with week day names
        apo_truck_load_df['requested_delivery_day_name'] = apo_truck_load_df["requested_delivery_date"].dt.day_name()
        apo_truck_load_df["requested_delivery_date"] = apo_truck_load_df["requested_delivery_date"].dt.strftime(constants.date_format)
        apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["requested_delivery_date"] >= self.model_parameters['start_date']]
        apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["requested_delivery_date"] <= self.model_parameters['end_date']]
        apo_truck_load_df["requested_delivery_period"] = apo_truck_load_df["requested_delivery_date"].apply(lambda x: self.date_to_period[x])

        apo_truck_load_df["delivery_date"] = pd.to_datetime(apo_truck_load_df["delivery_date"],format=constants.date_format)
        apo_truck_load_df['delivery_day_name'] = apo_truck_load_df["delivery_date"].dt.day_name()
        apo_truck_load_df["delivery_date"] = apo_truck_load_df["delivery_date"].dt.strftime(constants.date_format)
        apo_truck_load_df["original_delivery_date"] = apo_truck_load_df["delivery_date"]
        apo_truck_load_df["delivery_date"]  = np.where(apo_truck_load_df["delivery_date"]  < self.model_parameters['start_date'], self.model_parameters['start_date'],apo_truck_load_df["delivery_date"])
        apo_truck_load_df = apo_truck_load_df.loc[apo_truck_load_df["delivery_date"] <= self.model_parameters['end_date']]
        apo_truck_load_df["delivery_period"] = apo_truck_load_df["delivery_date"].apply(lambda x: self.date_to_period[x])

        apo_truck_load_df = apo_truck_load_df.rename(columns={'pallet_conversion_factor': 'units_per_pallet', 'weight_conversion_factor': 'weight_per_unit',
                     'volume_conversion_factor': 'volume_per_unit'})

        value_columns = ['dc','dc_name','requested_delivery_date','atp_availability_date','delivery_date','actual_delivery_date','original_delivery_date','pallet_spot','gross_weight','confirmed_quantity_in_base_unit',
                         'volume','requested_delivery_period','delivery_period','requested_delivery_day_name','delivery_day_name','priority_line_flag',
                         'units_per_pallet','weight_per_unit','volume_per_unit','base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date',
                         'order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','shuffle_together_flag']

        self.apo_truck_load_df = apo_truck_load_df
        apo_truck_load_dict = {}
        for index, row in apo_truck_load_df.iterrows():
            if row['po_number'] not in apo_truck_load_dict:
                apo_truck_load_dict[row['po_number']] = {}
            if (row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material']) not in apo_truck_load_dict[row['po_number']]:
                apo_truck_load_dict[row['po_number']][(row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material'])] = {}

            apo_truck_load_dict[row['po_number']][(row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material'])] = dict((k, row[k]) for k in value_columns)

        return apo_truck_load_dict

    def read_truck_capacity_details(self):
        truck_capacity_details_df = self.input_tables_dict['truck_capacity_details']

        truck_capacity_details_df["requested_delivery_date"] = pd.to_datetime(truck_capacity_details_df["requested_delivery_date"],format=constants.date_format)
        # Create new column with week day names
        truck_capacity_details_df['requested_delivery_day_name'] = truck_capacity_details_df["requested_delivery_date"].dt.day_name()
        truck_capacity_details_df["requested_delivery_date"] = truck_capacity_details_df["requested_delivery_date"].dt.strftime(constants.date_format)
        truck_capacity_details_df = truck_capacity_details_df.loc[truck_capacity_details_df["requested_delivery_date"] >= self.model_parameters['start_date']]
        truck_capacity_details_df = truck_capacity_details_df.loc[truck_capacity_details_df["requested_delivery_date"] <= self.model_parameters['end_date']]
        truck_capacity_details_df["requested_delivery_period"] = truck_capacity_details_df["requested_delivery_date"].apply(lambda x: self.date_to_period[x])

        key_columns = ['po_number']
        value_columns = list(set(truck_capacity_details_df.columns.tolist()) - set(key_columns))
        self.truck_capacity_details_df = truck_capacity_details_df
        truck_capacities = {}
        truck_po_level_details = {}
        for index, row in truck_capacity_details_df.iterrows():
            if row['trailer_size'] not in truck_capacities:
                truck_capacities[row['trailer_size']] = {}
            truck_capacities[row['trailer_size']] = {'weight_capacity':row['weight_constraint'],'volume_capacity':row['volume_constraint'],'pallet_capacity':row['pallet_constraint']}

            if row['po_number'] not in truck_po_level_details:
                truck_po_level_details[row['po_number']] = {}
            truck_po_level_details[row['po_number']] = dict((k, row[k]) for k in value_columns)
            truck_po_level_details[row['po_number']]['under_utilization_cost'] = 100 - max((row['total_weight_size_occupied'] / row['weight_constraint']),(row['total_volume_size_occupied'] / row['volume_constraint']),(row['total_pallet_size_occupied'] / row['pallet_constraint'])) * 100

        return truck_capacities, truck_po_level_details

    def read_dc_slot_schedule(self):
        dc_slot_schedule_df = self.input_tables_dict['dc_slot_schedule']
        already_scheduled_trucks = self.truck_details_fully_utilized
        garbage_truck_count = len(self.input_tables_dict['left_over_truck_capacity_details'])

        if garbage_truck_count > 0:
            self.garbage_truck_po_number = self.input_tables_dict['left_over_truck_capacity_details']['po_number'].unique()[0]
            dc_slot_schedule_df, self.garbage_truck_period = reduce_slots_for_leftover_truck(dc_slot_schedule_df, self.horizon, self.period_day_name_mapping)

        if len(already_scheduled_trucks) > 0:
            already_scheduled_trucks["requested_delivery_date"] = pd.to_datetime(already_scheduled_trucks["requested_delivery_date"], format=constants.date_format)
            # Create new column with week day names
            already_scheduled_trucks['requested_delivery_day_name'] = already_scheduled_trucks["requested_delivery_date"].dt.day_name()
            already_scheduled_trucks["requested_delivery_date"] = already_scheduled_trucks["requested_delivery_date"].dt.strftime(constants.date_format)
            already_scheduled_trucks = already_scheduled_trucks.loc[already_scheduled_trucks["requested_delivery_date"] >= self.model_parameters['start_date']]
            already_scheduled_trucks = already_scheduled_trucks.loc[already_scheduled_trucks["requested_delivery_date"] <= self.model_parameters['end_date']]
            already_scheduled_trucks["requested_delivery_period"] = already_scheduled_trucks["requested_delivery_date"].apply(lambda x: self.date_to_period[x])
            already_scheduled_trucks = already_scheduled_trucks.groupby('requested_delivery_day_name').size().reset_index(name='count')

        already_scheduled_trucks_dict = {}
        for index, row in already_scheduled_trucks.iterrows():
            already_scheduled_trucks_dict[row['requested_delivery_day_name']] = row['count']

        dc_slot_schedule_dict = {}
        for index, row in dc_slot_schedule_df.iterrows():
            slk = already_scheduled_trucks_dict[row['week_name']] if row['week_name'] in already_scheduled_trucks_dict else 0
            avl = (row['number_of_slots'] - slk) if (row['number_of_slots'] - slk) > 0 else 0
            dc_slot_schedule_dict[row['week_name']] = avl

        return dc_slot_schedule_dict

    def create_apo_truck_load_combinations(self):
        order_allocation_combinations = {}
        order_with_no_slots = {}
        for po_number, po_values in self.apo_truck_load_dict.items():
            for key, values in po_values.items():
                sales_document, sales_document_item, schedule_line, material = key
                if values['priority_line_flag'] == 'Y':
                    if values['requested_delivery_period'] <= values['delivery_period']:
                        period_lst = []
                        result = find_valid_period(values['delivery_period'], self.horizon, self.period_day_name_mapping, self.dc_slot_schedule_dict)
                        if result is not None:
                            period_lst.append(result)
                    else:
                        period_lst = []
                        # Try within requested window
                        for period in range(values['delivery_period'], values['requested_delivery_period'] + 1):
                            day_name = self.period_day_name_mapping[period]['day_name']
                            if self.dc_slot_schedule_dict.get(day_name, 0) > 0:
                                period_lst.append(period)

                        # If nothing found, fallback after requested
                        if not period_lst:
                            result = find_valid_period(values['requested_delivery_period'], self.horizon, self.period_day_name_mapping, self.dc_slot_schedule_dict)
                            if result is not None:
                                period_lst.append(result)
                else:
                    period_lst = list(range(1,self.horizon+1))
                has_valid_slot = False
                for po in self.truck_po_level_details.keys():
                    for period in period_lst:
                        if period >= values['delivery_period']:
                            if self.period_day_name_mapping[period]['day_name'] in self.dc_slot_schedule_dict:
                                if self.dc_slot_schedule_dict[self.period_day_name_mapping[period]['day_name']] > 0:
                                    order_allocation_combinations[(sales_document, sales_document_item, schedule_line, material, po_number, po, period)] = values
                                    has_valid_slot = True

                if not has_valid_slot:
                    order_with_no_slots[(sales_document, sales_document_item, schedule_line, material, po_number)] = values

        logger.info("Order Allocation Combinations Created with {} combinations".format(len(order_allocation_combinations)))

        truck_selection_combinations = {}
        order_truck_mapping = {}
        period_truck_mapping = {}
        truck_period_mapping = {}
        original_truck_order_mapping = {}
        order_selection_mapping_dict = {}
        shuffle_together_mapping_dict = {}
        shuffle_order_schedule_line_mapping_dict = {}
        for key, values in order_allocation_combinations.items():
            sales_document, sales_document_item, schedule_line, material, po_number, po, period = key
            if (po, period) not in truck_selection_combinations:
                truck_selection_combinations[(po, period)] = []
            truck_selection_combinations[(po, period)].append(key)

            if period not in period_truck_mapping:
                period_truck_mapping[period] = set()
            period_truck_mapping[period].add(po)

            if po not in truck_period_mapping:
                truck_period_mapping[po] = set()
            truck_period_mapping[po].add(period)

            if (sales_document, sales_document_item, schedule_line, material, po_number) not in order_truck_mapping:
                order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)] = []
            order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)].append((po, period))

            if (sales_document, sales_document_item, material, po_number) not in order_selection_mapping_dict:
                order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)] = {}
            if (po, period) not in order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)]:
                order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)] = set()
            order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)].add(schedule_line)

            if values['shuffle_together_flag'] == 'Y':
                if (sales_document, sales_document_item, material, po_number) not in shuffle_together_mapping_dict:
                    shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)] = {}
                if (po, period) not in shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)]:
                    shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)] = set()
                shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)].add(schedule_line)

                if (sales_document, sales_document_item, material, po_number) not in shuffle_order_schedule_line_mapping_dict:
                    shuffle_order_schedule_line_mapping_dict[(sales_document, sales_document_item, material, po_number)] = set()
                shuffle_order_schedule_line_mapping_dict[(sales_document, sales_document_item, material, po_number)].add(schedule_line)

            if (po, period) not in original_truck_order_mapping:
                original_truck_order_mapping[(po, period)] = set()
            if po_number == po:
                original_truck_order_mapping[(po, period)].add(key)

        return order_allocation_combinations, truck_selection_combinations, order_truck_mapping, period_truck_mapping, truck_period_mapping, original_truck_order_mapping, order_selection_mapping_dict, shuffle_together_mapping_dict, shuffle_order_schedule_line_mapping_dict, order_with_no_slots