try:
    from aera import session
except ImportError:
    session = None  # AERA not available in LOCAL mode

import glob as _glob
import pandas as pd
import os
from src.common.constants import data_column_mapping
from src.stage_one.pre_processing.data_handling import fix_column_names, get_string_columns_mapping
from src.common.logger_config import logger
import math


def convert_dict(df, data_column_mapping):
    for col in data_column_mapping.keys():
        if data_column_mapping[col]['type'] == "string":
            try:
                if df[col].dtype == float:
                    df[col] = df[col].astype('Int64').astype(str)
                else:
                    df[col] = df[col].astype(str)
            except:
                pass
    return df


def normalize_dc_column(df, key):
    """Strip leading zeros from 'dc' in dc_slot_schedule to match all other tables.

    The AERA data view delivers dc_slot_schedule with DC zero-padded to 10 digits
    (e.g. '0001000001'); all other tables use the bare 7-digit form ('1000001').
    Using astype(str) first makes the function safe regardless of whether the
    column arrived as string or int.
    """
    if key == 'dc_slot_schedule' and 'dc' in df.columns:
        df['dc'] = df['dc'].astype(str).str.lstrip('0')
    return df


def normalize_string_dtypes(df, key):
    """Cast to str any column that data_column_mapping marks as 'type':'string'
    but arrived as a non-object dtype (e.g. int64 from the AERA SDK or pd.read_csv).

    Converts display-name keys (e.g. 'Sales Document') to snake_case to match
    column names after fix_column_names has run.
    """
    str_cols = {
        k.lower().strip().replace(' ', '_')
        for k, v in data_column_mapping.get(key, {}).items()
        if v['type'] == 'string'
    }
    for col in str_cols:
        if col in df.columns and df[col].dtype != object:
            df[col] = df[col].astype(str)
    return df


# ---------------------------------------------------------------------------
# LOCAL mode — reads CSVs from input_data/, skipping the "Filters and FollowUps"
# metadata block that AERA UI exports prepend to every file.
# ---------------------------------------------------------------------------

# Maps the dict key used in input_tables_dict to the CSV filename glob pattern.
_LOCAL_CSV_PATTERNS = {
    'apo_truck_load':          'APO_Truckload_*.csv',
    'truck_capacity_details':  'TRUCKLOAD_UTILIZATION_*.csv',
    'dc_slot_schedule':        'DC_Slot_Schedule_*.csv',
    'general_configurations':  'General_Configurations_*.csv',
}


def _find_header_row(filepath):
    """Return the 0-based line index of the real CSV header row.

    AERA UI exports begin with a "Filters and FollowUps" block followed by a
    blank line; the actual header comes on the line after that blank.  Files
    without the block start at row 0.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if line.strip() == '':
                return i + 1  # header is the line immediately after the blank
    return 0  # no blank found → no Filters block, header is at row 0


class LocalDataSource:
    """LOCAL mode data reader — same output contract as DataSDK.read_data().

    Returns (data_dict, files_read_status) where data_dict is
    {table_key: DataFrame} with columns normalized by fix_column_names.
    """

    def __init__(self, input_data_path):
        self.input_data_path = input_data_path

    def read_data(self):
        data_dict = {}
        files_read_status = True

        for key, pattern in _LOCAL_CSV_PATTERNS.items():
            matches = _glob.glob(os.path.join(self.input_data_path, pattern))
            if not matches:
                logger.warning(f"[LOCAL] No CSV found for '{key}' (pattern: {pattern})")
                col_names = [c.lower().replace(' ', '_') for c in data_column_mapping[key]]
                data_dict[key] = pd.DataFrame(columns=col_names)
                files_read_status = False
                continue

            filepath = matches[0]
            header_row = _find_header_row(filepath)
            logger.info(f"[LOCAL] Reading '{key}' from {os.path.basename(filepath)} (skiprows={header_row})")

            try:
                string_columns = get_string_columns_mapping(key)
                if string_columns:
                    df = pd.read_csv(filepath, skiprows=header_row, dtype=string_columns)
                else:
                    df = pd.read_csv(filepath, skiprows=header_row)
                df = fix_column_names(convert_dict(df, data_column_mapping[key]))
                df = normalize_dc_column(df, key)
                df = normalize_string_dtypes(df, key)
                data_dict[key] = df
                logger.info(f"[LOCAL] Loaded '{key}': {len(df)} rows, columns={list(df.columns)}")
            except Exception as exc:
                logger.warning(f"[LOCAL] Failed to read {filepath}: {exc}")
                col_names = [c.lower().replace(' ', '_') for c in data_column_mapping[key]]
                data_dict[key] = pd.DataFrame(columns=col_names)
                files_read_status = False

        return data_dict, files_read_status


# ---------------------------------------------------------------------------
# AERA mode — original DataSDK (unchanged)
# ---------------------------------------------------------------------------

class DataSDK:
    """
    DataSDK will perform operations like read, download, through SDK
    """

    def __init__(self, params, request_body, workspace="cortex-optimization"):

        self.workspace = workspace
        self.project_id = params["project_id"]
        self.sdk_session = session.get_session(**params).create_client("dwb")
        self.process = session.get_session(**params).create_client('process')
        self.data_mapping = request_body['data_mapping']
        self.path = request_body['path']
        self.request_body = request_body

    def download_data_using_web_api(self):
        page_size = 10000
        for key,value in self.data_mapping.items():
            api_name = value['api_name']
            try:
                data = self.sdk_session.read_report(workspace=self.workspace,reportName=api_name, columnNameAs="DISPLAY_NAME",pageSize=page_size)
                total_report_rows = data["metaData"]["totalReportRows"]
                final_report_data = data.get("data")
                if total_report_rows > page_size:
                    if "nextPageURL"  in data["metaData"]:
                        next_page_url = data["metaData"]["nextPageURL"]
                    else:
                        next_page_url = False
                    no_of_pages = math.ceil(total_report_rows / page_size)
                else:
                    next_page_url = False
                    no_of_pages = math.ceil(total_report_rows / total_report_rows)
                for page in range(1, no_of_pages):
                    print(page, next_page_url)
                    if next_page_url:
                        page_data = self.sdk_session.read_report(nextPageURL=next_page_url)
                        final_report_data.extend(page_data["data"][1:])
                        next_page_url = page_data["metaData"].get("nextPageURL")
                dataframe = pd.DataFrame(final_report_data[1:])
                columns = final_report_data[0]  #
                dataframe.columns =  columns
                file_path = str(os.path.join(self.path, key +".csv"))
                value['file_path'] = file_path
                value['status'] = True
                if len(dataframe) <= 0:
                    dataframe = pd.DataFrame(columns=data_column_mapping[key].keys())
                print(dataframe.columns)
                dataframe.to_csv(file_path, index=False)
                self.data_mapping[key] = value
                logger.info("Report Download Complete for Report : {}".format(key))
            except:
                logger.info("Report Download Exception for Report : {}".format(key))
                file_path = 'Data Download Exception'
                value['file_path'] = file_path
                value['status'] = False
                self.data_mapping[key] = value
        self.request_body['data_mapping'] = self.data_mapping
        return self.request_body

    def download_data_using_dataset(self):
        for key,value in self.data_mapping.items():
            api_name = value['api_name']
            try:
                temp_lst = []
                dataset = self.sdk_session.read_dataset(workspaceName=self.workspace,dataSetName=api_name,filter=None, pageNumber=0,pageSize=10000)
                column_name_mapping = {i['technicalName']: i['displayName'] for i in dataset["read_dataset"]['data']['fields']}
                if dataset["read_dataset"]["statusCode"] == 200:
                    tota_num_of_pages = dataset["read_dataset"]['data']['totalNumberOfPages']
                    for p in range(0, tota_num_of_pages):
                        dataset = self.sdk_session.read_dataset(workspaceName=self.workspace, dataSetName=api_name,filter=None, pageNumber=p, pageSize=10000)
                        df = pd.DataFrame(dataset["read_dataset"]['data']['data'])
                        df = df.rename(columns=column_name_mapping)
                        temp_lst.append(df)
                dataframe = pd.concat(temp_lst)
                file_path = str(os.path.join(self.path, key +".csv"))
                value['file_path'] = file_path
                value['status'] = True
                if len(dataframe) <= 0:
                    dataframe = pd.DataFrame(columns=data_column_mapping[key].keys())
                print(dataframe.columns)
                dataframe.to_csv(file_path, index=False)
                self.data_mapping[key] = value
                logger.info("Report Download Complete for Report : {}".format(key))
            except:
                logger.info("Report Download Exception for Report : {}".format(key))
                file_path = 'Data Download Exception'
                value['file_path'] = file_path
                value['status'] = False
                self.data_mapping[key] = value
        self.request_body['data_mapping'] = self.data_mapping
        return self.request_body

    def download_data_using_subject_area(self):
        for key,value in self.data_mapping.items():
            api_name = value['api_name']
            try:
                temp_lst = []
                subject_area = self.sdk_session.read_subject_area(workspaceName=self.workspace, subjectAreaName=api_name,filter=None, pageNumber=0,pageSize=10000)
                column_name_mapping = {i['technicalName']: i['displayName'] for i in subject_area["read_subject_area"]['data']['fields']}
                if subject_area["read_subject_area"]["statusCode"] == 200:
                    tota_num_of_pages = subject_area["read_subject_area"]['data']['totalNumberOfPages']
                    for p in range(0, tota_num_of_pages):
                        subject_area = self.sdk_session.read_subject_area(workspaceName=self.workspace,subjectAreaName=api_name, filter=None,pageNumber=p, pageSize=10000)
                        df = pd.DataFrame(subject_area["read_subject_area"]['data']['data'])
                        df = df.rename(columns=column_name_mapping)
                        temp_lst.append(df)
                dataframe = pd.concat(temp_lst)
                file_path = str(os.path.join(self.path, key +".csv"))
                value['file_path'] = file_path
                value['status'] = True
                if len(dataframe) <= 0:
                    dataframe = pd.DataFrame(columns=data_column_mapping[key].keys())
                print(dataframe.columns)
                dataframe.to_csv(file_path, index=False)
                self.data_mapping[key] = value
                logger.info("Report Download Complete for Report : {}".format(key))
            except:
                logger.info("Report Download Exception for Report : {}".format(key))
                file_path = 'Data Download Exception'
                value['file_path'] = file_path
                value['status'] = False
                self.data_mapping[key] = value
        self.request_body['data_mapping'] = self.data_mapping
        return self.request_body

    def read_data(self):
        data_dict = {}
        files_read_status = True
        self.data_mapping = self.request_body['data_mapping']
        for key, value in self.data_mapping.items():
            if value['status']:
                try:
                    string_columns = get_string_columns_mapping(key)
                    if len(string_columns) > 0:
                        df = pd.read_csv(value['file_path'],dtype=string_columns)
                    else:
                        df = pd.read_csv(value['file_path'])
                    df = fix_column_names(convert_dict(df, data_column_mapping[key]))
                    df = normalize_dc_column(df, key)
                    df = normalize_string_dtypes(df, key)
                    data_dict[key] = df
                except:
                    column_names = data_column_mapping[key].keys()
                    df = pd.DataFrame(columns=column_names)
                    df = fix_column_names(convert_dict(df, data_column_mapping[key]))
                    files_read_status = False
                    data_dict[key] = df
            else:
                column_names = data_column_mapping[key].keys()
                df = pd.DataFrame(columns=column_names)
                df = fix_column_names(convert_dict(df, data_column_mapping[key]))
                files_read_status = False
                data_dict[key] = df
        return data_dict, files_read_status
