import math
import numpy as np
import pandas as pd
import os
try:
    from aera import session
except ImportError:
    session = None  # AERA not available in LOCAL mode
from src.write_back_results.utilities import CommonUtility
import base64
from src.common.logger_config import logger


class DatasetHandling:
    """
    This class provides the methods to handle the dataset for given subject area
    """

    def __init__(self, params, workspace="cortex-optimization"):
        """
        :param str service_id: Id of the service
        :param dict params: parameters required to create the cortex sdk session
        :param str workspace: Name of workspace under which dataset and subject area should be created
        """
        self.workspace = workspace
        self.project_id = params["project_id"]
        self.sdk_session = session.get_session(**params).create_client("dwb")
        self.process = session.get_session(**params).create_client('process')

    @staticmethod
    def get_column_config(csv_data: pd.DataFrame, columns_datatype_dict=None):

        supported_datatypes = {
            "float64": "double",
            "int64": "numeric",
            "str": "string",
            "int": "numeric",
            "float": "double",
            "bool": "boolean",
            "object": "string",
        }

        if len(csv_data) > 0:
            column_max_length = dict([(v, int(csv_data[v].apply(lambda r: len(str(r)) if r is not None else 0).max())) for v in csv_data.columns.values])
        else:
            column_max_length = dict([(v, csv_data[v].apply(lambda r: len(str(r)) if r is not None else 0).max()) for v in csv_data.columns.values])
        column_types = dict(csv_data.dtypes)

        column_config = []
        for key, _ in column_types.items():
            if columns_datatype_dict and key in columns_datatype_dict:
                column_data_type = columns_datatype_dict[key]
            else:
                try:
                    column_data_type = column_types.get(key).name
                except Exception as e:
                    print(e)
                    column_data_type = column_types.get(key)
            column_data_type = supported_datatypes.get(column_data_type) if column_data_type in list(
                supported_datatypes.keys()) else column_data_type
            scale = 5 if column_data_type in ["float", "int", "double"] else 0

            data_length = column_max_length.get(key) if not math.isnan(column_max_length.get(key)) else 0
            if column_data_type == "string":
                data_length = column_max_length.get(key) if not math.isnan(column_max_length.get(key)) else 256
            elif column_data_type == "numeric":
                data_length = column_max_length.get(key) if not math.isnan(column_max_length.get(key)) else 10

            column_info = {
                "name": "date_" if key.strip() == "date" else key.strip(),
                "dataType": column_data_type.title(),
                "dataLength": data_length,
                "scale": scale
            }
            column_config.append(column_info)
        return [column_config]

    def create_dataset_from_file(self, name, description, destination_path, dataset_file_path, columns_datatype_dict=None, delimiter=',', append_data=True, project_id=None, plan_id=None):
        """
        To create the dataset at given location for the given source dataset file
        :param str name: Name of dataset
        :param str description: Description for the given dataset
        :param str destination_path: Hierarchy at which the dataset should be created on the Aera Developer UI
        :param str dataset_file_path: A csv / gz file present in the client’s local machine which contains data
        :param dict columns_datatype_dict: Datatype of columns of dataset
        :param str delimiter: delimiter of dataset
        """
        csv_data = pd.read_csv(dataset_file_path, sep=delimiter)
        column_config = self.get_column_config(csv_data, columns_datatype_dict)
        logger.info(f"Got Column Config")
        print(column_config)
        total_file_size = CommonUtility.get_file_size(dataset_file_path, "gb")
        logger.info(f"total_file_size {total_file_size}")
        if total_file_size >= 10.0:
            number_of_chunks = math.ceil(total_file_size / 1024)
            df = pd.read_csv(dataset_file_path)
            create_dataset_response = None
            for idx, chunk in enumerate(np.array_split(df, number_of_chunks)):
                chunk_file_path = f'/tmp/chunk_file_{name}.csv'
                chunk.to_csv(chunk_file_path, sep=delimiter, index=False)
                print(idx, chunk_file_path)
                logger.info(f"calling - sdk_session.create_dataset")
                create_dataset_response = self.sdk_session.create_dataset(workspaceName=self.workspace,
                                                                          dataSetName=name,
                                                                          description=description,
                                                                          folderPath=destination_path,
                                                                          file=dataset_file_path,
                                                                          isAppend=append_data,
                                                                          columnConfig=column_config,
                                                                          delimiter=delimiter
                                                                          )

        else:
            # TODO: Check if folder path already exists
            logger.info(f"calling - sdk_session.create_dataset")
            create_dataset_response = self.sdk_session.create_dataset(workspaceName=self.workspace,
                                                                      dataSetName=name,
                                                                      description=description,
                                                                      folderPath=destination_path,
                                                                      isAppend=append_data,
                                                                      file=dataset_file_path,
                                                                      columnConfig=column_config,
                                                                      delimiter=delimiter
                                                                      )

        return create_dataset_response

    def append_dataset(self, name, description, destination_path, dataset_file_path, columns_datatype_dict=None, delimiter=','):
        """
        To create the dataset at given location for the given source dataset file
        :param str name: Name of dataset
        :param str description: Description for the given dataset
        :param str destination_path: Hierarchy at which the dataset should be created on the Aera Developer UI
        :param str dataset_file_path: A csv / gz file present in the client’s local machine which contains data
        :param str delimiter: delimiter of dataset
        """

        total_file_size = CommonUtility.get_file_size(dataset_file_path, "gb")
        if total_file_size >= 10.0:
            number_of_chunks = math.ceil(total_file_size / 1024)
            df = pd.read_csv(dataset_file_path)
            create_dataset_response = None
            for idx, chunk in enumerate(np.array_split(df, number_of_chunks)):
                chunk_file_path = f'/tmp/chunk_file_{name}.csv'
                chunk.to_csv(chunk_file_path, index=False)
                print(idx, chunk_file_path)
                create_dataset_response = self.sdk_session.create_dataset(workspaceName=self.workspace,
                                                                          dataSetName=name,
                                                                          description=description,
                                                                          folderPath=destination_path,
                                                                          file=dataset_file_path,
                                                                          isAppend=True,
                                                                          delimiter=delimiter
                                                                          )

                print(create_dataset_response)
        else:
            # TODO: Check if folder path already exists
            create_dataset_response = self.sdk_session.create_dataset(workspaceName=self.workspace,
                                                                      dataSetName=name,
                                                                      description=description,
                                                                      folderPath=destination_path,
                                                                      file=dataset_file_path,
                                                                      isAppend=True,
                                                                      delimiter=delimiter
                                                                      )

        return create_dataset_response

    def truncate_dataset(self, project_id, plan_id, dataset_name):
        logger.info(f"Truncating {dataset_name}")
        logger.info(f"Calling sdk_session.get_metadata")
        meta_data = self.sdk_session.get_metadata(objectName=dataset_name, objectType="DATASET",workspaceName=self.workspace)
        table_name = meta_data["tableName"]
        process_params = {
            "project_id": self.project_id,
            "object_name": table_name,
            "object_type": "DATASET"
        }
        process_id = "F780942C_796C_40F6_8940_3DF18F4ECF90"

        logger.info(f"Calling process.run_process")
        resp = self.process.run_process(
            processId=process_id,
            processName=None,
            processType="sync",
            processParams=process_params
        )

        return resp

    def delete_data(self, project_id, plan_id, dataset_name,filters):
        logger.info(f"Deleting {dataset_name}")
        logger.info(f"Calling sdk_session.get_metadata")
        meta_data = self.sdk_session.get_metadata(objectName=dataset_name, objectType="DATASET",
                                                  workspaceName=self.workspace)
        table_name = meta_data["tableName"]
        query = "Delete from {0} where {1};".format(table_name,filters)
        query = query.encode('utf-8')
        query = base64.b64encode(query)
        query = query.decode('utf-8')
        process_params = {
            "project_id": self.project_id,
            "sdk_tbl_name": table_name,
            "complete_query": query,
            "sql_operation_type": "DELETE"
        }
        process_id = "7BB1DDE5_9788_4AF4_945D_B07C30F39D29"

        logger.info(f"Calling process.run_process")
        resp = self.process.run_process(
            processId=process_id,
            processName=None,
            processType="sync",
            processParams=process_params
        )
        return resp


    def read_dateset(self, name, page_number=0, page_size=20, data_filter=None):
        """
        To read the dataset
        :param str name: Dataset name
        :param int page_number: Page number from which data needs to be read
        :param int page_size: Number of records need to be read from each page
        :param str data_filter: Filter which we want to apply on dataset
        """
        dataset = self.sdk_session.read_dataset(workspaceName=self.workspace,
                                                dataSetName=name,
                                                filter=data_filter,
                                                pageNumber=page_number,
                                                pageSize=page_size)

        if "status" in dataset["read_dataset"] and dataset["read_dataset"]["status"] == "Failed":
            return pd.DataFrame()

        return pd.DataFrame(dataset["read_dataset"]['data']['data'])


class SubjectAreaHandling:
    """
    Class SubjectAreaHandling will provide methods to deal with Subject Area
    """

    def __init__(self, params, workspace="cortex-optimization"):
        """
        :param dict params: parameters required to create the cortex sdk session
        """
        self.workspace = workspace
        self.sdk_session = session.get_session(**params).create_client("dwb")

    def create_subject_area(self, name, description, dataset_name, destination_path):
        """
        To create the Subject Area
        :param str name: Subject Area name
        :param str description: Description for the given Subject Area
        :param str dataset_name: Dataset name from which Subject Area needs to be created
        :param str destination_path: The hierarchy at which the subject area should be created on the Aera Developer UI
        """
        try:
            meta_data = self.sdk_session.get_metadata(objectName=name, objectType="SUBJECTAREA",workspaceName=self.workspace)
            if "error" in meta_data:
                is_append = False
            else:
                is_append = True
        except:
            is_append = False

        subject_area = self.sdk_session.create_subject_area(
            workspaceName=self.workspace,
            subjectAreaName=name,
            description=description,
            dataSetName=dataset_name,
            folderPath=destination_path,
            isAppend=is_append
        )

        if "message" in subject_area['create_subject_area']:
            return False, subject_area

        return True, subject_area

    def append_subject_area(self, name, description, dataset_name, destination_path):
        """
        To append the records in the existing Subject Area
        :param str name: Subject Area name
        :param str description: Description for the given Subject Area
        :param str dataset_name: Dataset name from which Subject Area needs to be created
        :param str destination_path: The hierarchy at which the subject area should be created on the Aera Developer UI
        """
        subject_area = self.sdk_session.create_subject_area(
            workspaceName=self.workspace,
            subjectAreaName=name,
            description=description,
            dataSetName=dataset_name,
            folderPath=destination_path,
            isAppend=True
        )

        if "message" in subject_area['create_subject_area']:
            return False, subject_area

        return True, subject_area


class DataPopulation:
    """
    DataPopulation class will provide the methods to handle the output data population
    """

    def __init__(self, sdk_session_params, workspace="cortex-optimization"):
        self.sdk_session_params = sdk_session_params
        self.workspace = workspace

    def populate_data(self, dataset_name, dataset_file_path, dataset_dest_path, subject_area_name, subject_area_dest_path, columns_datatype_dict=None, delimiter=","):
        """
        To populate the final output data into fact tables.
        :param str dataset_name: Name of dataset
        :param str dataset_file_path: Path of data file
        :param str dataset_dest_path: Path at which dataset need to be created on Aera UI
        :param str subject_area_name: Name of subject area
        :param str subject_area_dest_path: Path at which subject area need to be created on Aera UI
        """

        # Creating dataset on Aera UI
        dh = DatasetHandling(self.sdk_session_params, self.workspace)
        r1 = dh.create_dataset_from_file(name=dataset_name,
                               description=dataset_name,
                               destination_path=dataset_dest_path,
                               dataset_file_path=dataset_file_path,
                               columns_datatype_dict=columns_datatype_dict,
                               delimiter=delimiter
                               )

        print(r1)

        # Subject area creation on Aera UI
        if "create_dataset" in r1 and "status" in r1["create_dataset"] and r1["create_dataset"]["status"] == "Failed":
            print(f"Could not created {dataset_name} !")
            return

        sbh = SubjectAreaHandling(self.sdk_session_params, self.workspace)
        r2 = sbh.create_subject_area(name=subject_area_name,
                                     description=subject_area_name,
                                     dataset_name=dataset_name,
                                     destination_path=subject_area_dest_path
                                     )

        print(r2)

    def upload_data_from_directory(self, plan_id, directory_path, data_stream_type="output"):
        data_stream_type = data_stream_type.lower().strip()
        dataset_destination_path = f"optimization/{data_stream_type}/{plan_id}"
        subject_area_destination_path = f"optimization/{data_stream_type}/{plan_id}"
        output_files = [file for file in os.listdir(directory_path) if file.endswith(".csv")]
        for file in output_files:
            dataset_file_path = os.path.join(directory_path, file)
            dataset_name = f"{file.split('.')[0]}_ds_{plan_id}"
            subject_area_name = f"{file.split('.')[0]}_sa_{plan_id}"

            print(f"Uploading {dataset_name} ............")
            self.populate_data(dataset_name, dataset_file_path, dataset_destination_path, subject_area_name, subject_area_destination_path)


def upload_data_sdk(project_id, plan_id, dataset_handler, upload_params, delimiter, truncate_flag, filters=None):
    dataset_name = upload_params["dataset_name"]
    description = upload_params["description"]
    destination_path = upload_params["destination_path"]
    dataset_file = upload_params["dataset_file"]
    append_data = upload_params["append_data"]
    if dataset_name in ['SALESORDERITEM_OUTPUT', 'SCHEDULELINE_OUTPUT', 'FINAL_ORDER_OUTPUT']:
        datatype_dict = {"materialbycustomer": "string"}
        columns_datatype_dict = {"scenario_id": "string", "materialbycustomer": "string"}
        df = pd.read_csv(dataset_file, sep=delimiter, dtype=datatype_dict)
    else:
        columns_datatype_dict = {"scenario_id": "string"}
        df = pd.read_csv(dataset_file, sep=delimiter)
    df.to_csv(dataset_file, index=False, sep=delimiter)

    if filters:
        dataset_handler.delete_data(project_id, plan_id, dataset_name,filters)
    if truncate_flag:
        dataset_handler.truncate_dataset(project_id, plan_id, dataset_name)
    res = dataset_handler.create_dataset_from_file(name=dataset_name,
                                                   description=description,
                                                   destination_path=destination_path,
                                                   dataset_file_path=dataset_file,
                                                   append_data=append_data,
                                                   columns_datatype_dict=columns_datatype_dict,
                                                   delimiter=delimiter,
                                                   project_id=project_id, plan_id=plan_id
                                                   )
    print(res)
    return res
