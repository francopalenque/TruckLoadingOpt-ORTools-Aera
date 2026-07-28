from src.common.logger_config import logger
import os
from src.write_back_results.aera_sdk import *


def write_lp(output_path, model):
    logger.info("Writing lp file")
    model.write(os.path.join(output_path, "LP.lp"))
    logger.info("Lp file written")


def write_mps(output_path, model):
    logger.info("Writing mps file")
    model.write(os.path.join(output_path, "MPS.mps"))
    logger.info("Mps file written")


def write_solution(output_path, model):
    logger.info("Writing Solution file")
    model.write(os.path.join(output_path, "SOL.sol"))
    logger.info("Solution file written")


def write_IIS_file(output_path, model):
    logger.info("Model is infeasible or unbounded")
    model.write(os.path.join(output_path, "LP.ilp"))
    logger.info("ILP file written")


def upload_output(project_id, plan_id,dataset_handler, sdk_destination_path,output_path, delimiter, truncate_flag):
    dataset_mapping = dict()
    dataset_mapping["FINAL_ORDER_OUTPUT"] = "finial_order_df.csv"
    dataset_mapping["SELECTED_TRUCK_DF"] = "sel_non_sel_df.csv"
    dataset_mapping["SALESORDERITEM_OUTPUT"] = "output_item.csv"
    dataset_mapping["SCHEDULELINE_OUTPUT"] = "output_schedule_line.csv"
    dataset_mapping["SUMMARY_OUTPUT"] = "summary_df.csv"
    upload_params = dict()
    upload_params["destination_path"] = sdk_destination_path
    upload_params["append_data"] = True
    upload_params["truncate_flag"] = True if truncate_flag == 'true' else False
    for dataset_name, file in dataset_mapping.items():
        try:
            upload_params["dataset_name"] = dataset_name
            upload_params["description"] = dataset_name
            upload_params["dataset_file"] = os.path.join(output_path, file)
            if os.path.exists(os.path.join(output_path, file)):
                res = upload_data_sdk(project_id, plan_id, dataset_handler, upload_params, delimiter, truncate_flag=upload_params["truncate_flag"])
                logger.info(f'Upload success of {res}')
                logger.info(f'Upload success of {file}')
            else:
                logger.info(f'File Missing of {file}')
        except Exception as e:
            logger.exception(f'Upload failed of {file}: {e}')


def upload_logs(project_id, plan_id,dataset_handler, sdk_destination_path,log_path, delimiter,truncate_flag):
    dataset_mapping = dict()
    dataset_mapping["SOLVER_1_LOGS"] = "log_file_formatted.csv"

    upload_params = dict()
    upload_params["destination_path"] = sdk_destination_path
    upload_params["append_data"] = True
    upload_params["truncate_flag"] = True if truncate_flag == 'true' else False
    for dataset_name, file in dataset_mapping.items():
        try:
            upload_params["dataset_name"] = dataset_name
            upload_params["description"] = dataset_name
            upload_params["dataset_file"] = os.path.join(log_path, file)
            if os.path.exists(os.path.join(log_path, file)):
                res = upload_data_sdk(project_id, plan_id, dataset_handler, upload_params, delimiter, truncate_flag=upload_params["truncate_flag"])
                logger.info(f'Upload success of {res}')
                logger.info(f'Upload success of {file}')
            else:
                logger.info(f'File Missing of {file}')
        except Exception as e:
            logger.exception(f'Upload failed of {file}: {e}')
