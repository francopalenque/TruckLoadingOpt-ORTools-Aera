import sys
import time
import datetime
import types
import os
import json
import shutil
import traceback
from contextlib import contextmanager

import pandas as pd

from src.common.logger_config import StreamToLoguru, logger
from src.common.constants import (
    RUN_MODE, LOCAL_INPUT_PATH, LOCAL_OUTPUT_PATH, BASE_DIR,
    finial_output, finial_output_stage_one, finial_output_stage_two,
    output_files_col, activate_stage_two, stage_one_reshuffling, stage_two_reshuffling,
)
from src.common.constants import *
from src.common.utils import create_folder, output_file_restructure, clear_model
from src.common.utilities import upload_output, upload_logs

# ---------------------------------------------------------------------------
# Optional AERA / Gurobi imports — absent in LOCAL mode
# ---------------------------------------------------------------------------
# _aera_session is no longer called for Seam 2; kept for potential future AERA use.
try:
    from aera import session as _aera_session
except ImportError:
    _aera_session = None

try:
    import gurobipy
except ImportError:
    # No Gurobi license: inject the OR-Tools shim so model-building imports
    # (`from gurobipy import GRB, LinExpr, min_`) resolve to working objects.
    from src.common.gurobi_compat import (
        GRB as _GRBShim,
        LinExpr as _LinExprShim,
        min_ as _min_shim,
    )
    _gurobi_stub = types.ModuleType('gurobipy')
    _gurobi_stub.GRB = _GRBShim
    _gurobi_stub.LinExpr = _LinExprShim
    _gurobi_stub.min_ = _min_shim
    sys.modules['gurobipy'] = _gurobi_stub

# ---------------------------------------------------------------------------
# All model-building imports come AFTER the gurobipy stub injection above
# ---------------------------------------------------------------------------
from src.stage_one.pre_processing.data_handling import (
    DataHandling, transform_date, create_data_dictionary,
    remove_files_in_folder, filter_dataframe, get_dc_list,
)
from src.stage_one.post_processing.post_processing import PostProcessor
from src.stage_one.model_building.model_building import OptimizationModel
from src.pre_processing.Data2 import DataSDK, LocalDataSource
from src.write_back_results.aera_sdk import DatasetHandling
from src.stage_two.pre_processing.data_handling import DataHandlingStageTwo
from src.stage_two.model_building.model_building import OptimizationModelStageTwo
from src.stage_two.post_processing.post_processing import PostProcessorStageTwo
from src.post_processing.post_processing import PostProcessorAnalysis, InputPostProcessor
from src.stage_one.model_building.reshuffling_allocation_model import ReshufflingStageOneModelConstruction
from src.stage_two.model_building.reshuffling_allocation_model import ReshufflingStageTwoModelConstruction


# ===========================================================================
# Seam 2 — Solver context manager factory
#
# In AERA mode: wraps the real optimizer_client.native_methods().
# In LOCAL mode: yields a _LocalOptClient whose .model is a gurobi_compat.Model
#   backed by OR-Tools/SCIP.
# ===========================================================================

class LocalSolverNotImplemented(NotImplementedError):
    """Kept for backwards-compatibility; no longer raised in Fase 2."""


class _LocalOptClient:
    def __init__(self):
        from src.common.gurobi_compat import Model as _ShimModel
        self.model = _ShimModel()


@contextmanager
def _local_optimizer_ctx():
    yield _LocalOptClient()


def _get_optimizer_ctx():
    """Return the OR-Tools/SCIP context manager — always, regardless of RUN_MODE.
    RUN_MODE now governs only Seam 1 (data read) and Seam 3 (write-back).
    """
    return _local_optimizer_ctx()


# ===========================================================================
# Main entry point
# ===========================================================================

def handle(req, **kwargs):
    """handle a request to the function
    Args:
        req (str): request body(Note: This will always comes in string format)
    Return:
        dict/list/None: return a JSON Compatible object which can be dumped into json
    """

    # Do not edit the helper sections unless needed
    # Helper section to set up Aera API/SDK
    if RUN_MODE == 'AERA':
        if kwargs.get("aerasdk_session"):
            logger.info("Got Aera API/SDK Session")
            sdk_session = kwargs['aerasdk_session']
        else:
            logger.error("Aera SDK/API Session not Found")
    else:
        logger.info(f"[RUN_MODE=LOCAL] Skipping AERA SDK session setup")

    # Helper section to load input data
    request_data = json.loads(req)  # req args are in json string, convert them to dictionary.
    logger.info(f"Input data received for function: {kwargs.get('function_name')}")
    logger.info(json.dumps(request_data, indent=4))

    summary_details = []
    local_run = (RUN_MODE == 'LOCAL')

    try:
        with _get_optimizer_ctx() as opt_client:
            # Model Start details.
            program_start_time = time.time()

            # Get Job details.
            project_id = request_data['project_id']
            plan_id = request_data['plan_id']
            apo_truck_load = request_data['apo_truck_load']
            truck_capacity_details = request_data['truck_capacity_details']
            dc_slot_schedule = request_data['dc_slot_schedule']
            general_configurations = request_data['general_configurations']
            delimiter = request_data['delimiter']
            truncate_flag = request_data['truncate_flag']
            sdk_workspace = request_data['sdk_workspace']
            sdk_destination_path = request_data['sdk_destination_path']

            # Internal Parameters
            download_type = 'SDK_WebApi' # 'Subject_Area', 'DataSet', 'SDK_WebApi'

            # Create Folder to store input, output and logs
            if local_run:
                output_path = LOCAL_OUTPUT_PATH
                logs_path = os.path.join(LOCAL_OUTPUT_PATH, 'logs')
                input_path = LOCAL_INPUT_PATH
                stage_one_output_path = os.path.join(LOCAL_OUTPUT_PATH, 'stage_one')
                stage_two_output_path = os.path.join(LOCAL_OUTPUT_PATH, 'stage_two')
                for p in [logs_path, stage_one_output_path, stage_two_output_path]:
                    create_folder(p)
            else:
                logs_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'logs')
                create_folder(logs_path)
                remove_files_in_folder(logs_path, '.csv')

            # Step 1: Write CSV header with pandas
            log_file_df = pd.DataFrame(columns=["Level", "Timestamp", "File", "Function", "Line", "Message"])
            log_file_df.to_csv(os.path.join(str(logs_path), 'log_file.csv'), index=False, sep="@")
            # Step 2: Configure Loguru to append logs in the same structure
            logger.add(os.path.join(str(logs_path), 'log_file.csv'), format="{level:<8}@{time:YY/MM/DD HH:mm}@{file:<15}@{function:<15}@{line:<5}@{message!r}")

            if not local_run:
                input_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'input')
                create_folder(input_path)
                output_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'output')
                create_folder(output_path)

            logger.info("Run Started For Plan ID : {}".format(plan_id))

            # Read Data
            if local_run:
                # ----- Seam 1: LOCAL -----
                logger.info("[LOCAL] Reading input data from CSV files")
                reading_input_data_start_time = time.time()
                local_src = LocalDataSource(LOCAL_INPUT_PATH)
                input_tables_dict, _ = local_src.read_data()
                input_tables_dict = transform_date(input_tables_dict)
                logger.info("Completed Reading Input Data in {} seconds".format(
                    round(time.time() - reading_input_data_start_time, 2)))
            else:
                request_body = {
                    "data_mapping": {
                        'apo_truck_load':           {'api_name': apo_truck_load},
                        'general_configurations':   {'api_name': general_configurations},
                        'truck_capacity_details':   {'api_name': truck_capacity_details},
                        'dc_slot_schedule':         {'api_name': dc_slot_schedule},
                    },
                    "path": input_path,
                    "project_id": project_id,
                    "plan_id": plan_id,
                }
                logger.info(f"request_body : {request_body}")

                cortex_sdk_params = {"project_id": project_id}
                logger.info(f"cortex_sdk_params : {cortex_sdk_params}")

                reading_input_data_start_time = time.time()
                input_tables_dict = {}
                if download_type == 'Subject_Area':
                    data_sdk = DataSDK(cortex_sdk_params, request_body, workspace=sdk_workspace)
                    request_body = data_sdk.download_data_using_subject_area()
                    input_tables_dict, file_read_status = data_sdk.read_data()
                elif download_type == 'DataSet':
                    data_sdk = DataSDK(cortex_sdk_params, request_body, workspace=sdk_workspace)
                    request_body = data_sdk.download_data_using_dataset()
                    input_tables_dict, file_read_status = data_sdk.read_data()
                elif download_type == 'SDK_WebApi':
                    data_sdk = DataSDK(cortex_sdk_params, request_body, workspace=sdk_workspace)
                    request_body = data_sdk.download_data_using_web_api()
                    input_tables_dict, file_read_status = data_sdk.read_data()

                input_tables_dict = transform_date(input_tables_dict)
                logger.info("Completed Reading Input Data in {} seconds".format(
                    round(time.time() - reading_input_data_start_time, 2)))

            dc_list, input_tables_dict = get_dc_list(input_tables_dict)

            # To redirect console logs to log file
            sys.stdout = StreamToLoguru()
            sys.stderr = StreamToLoguru()

            if not local_run:
                stage_one_output_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'output', 'stage_one')
                create_folder(stage_one_output_path)
                stage_two_output_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'output', 'stage_two')
                create_folder(stage_two_output_path)

            # ----- Seam 2: model/solver configuration -----
            opt_client.model.ModelName = "Hershey_TruckLoading_Optimization"
            opt_client.model.setParam('MIPGap', 0.001)  # 1% gap
            opt_client.model.setParam("TimeLimit", 180)

            for dc in dc_list:
                dc_start_time = time.time()
                logger.info(f"Started Building Optimization model for DC: {dc}")

                # Filter input data for the current DC
                dc_input_tables_dict, apo_truck_load_fully_utilized, truck_details_fully_utilized, actual_truck_count = filter_dataframe(input_tables_dict, dc)

                if len(dc_input_tables_dict['truck_capacity_details']) > 1:
                    # Data Pre Processing
                    logger.info("Starting Data Pre-Processing")
                    data_pre_processing_start_time = time.time()
                    input_data = DataHandling(project_id, plan_id, dc_input_tables_dict, input_path, truck_details_fully_utilized)
                    input_data.prepare_model_data()
                    logger.info("Completed Data Pre-Processing in {} seconds".format(round(time.time() - data_pre_processing_start_time, 2)))

                    # ── TEMP DIAG S1 (remove after diagnosis) ──────────────────
                    if dc == '1000002':
                        logger.info(f"[DIAG-S1] horizon={input_data.horizon}")
                        logger.info(f"[DIAG-S1] dc_slot_schedule_dict={input_data.dc_slot_schedule_dict}")
                        logger.info(f"[DIAG-S1] order_alloc_combos={len(input_data.order_allocation_combinations)}")
                        logger.info(f"[DIAG-S1] truck_sel_combos={len(input_data.truck_selection_combinations)}")
                        logger.info(f"[DIAG-S1] order_with_no_slots={len(input_data.order_with_no_slots)}")
                    # ── END TEMP DIAG S1 ────────────────────────────────────────

                    # Started Building and Solving Optimization Model
                    logger.info("Starting Building and Solving Optimization Model")
                    model_building_solve_start_time = time.time()
                    model_construction = OptimizationModel(input_data, opt_client.model, output_path)
                    opt_client.model, raw_output_dict = model_construction.build_solve_model()
                    logger.info("Completed Building and Solving Optimization Model in {} seconds".format(round(time.time() - model_building_solve_start_time, 2)))
                    # ── TEMP DIAG S1 (remove after diagnosis) ──────────────────
                    if dc == '1000002':
                        _alloc = raw_output_dict.get('order_allocation_dict', {})
                        _n_alloc = sum(1 for v in _alloc.values() if v >= 0.5)
                        _truck = raw_output_dict.get('truck_selection_dict', {})
                        _n_truck = sum(1 for v in _truck.values() if v >= 0.5)
                        logger.info(f"[DIAG-S1] raw_status={raw_output_dict.get('stage_one_opt_run_status')}")
                        logger.info(f"[DIAG-S1] order_alloc: total={len(_alloc)}, assigned={_n_alloc}")
                        logger.info(f"[DIAG-S1] truck_sel: total={len(_truck)}, selected={_n_truck}")
                        for _k, _v in raw_output_dict.get('kpi_dict', {}).items():
                            logger.info(f"[DIAG-S1] KPI {_k}={_v:.6f}")
                    # ── END TEMP DIAG S1 ────────────────────────────────────────
                    # Remove all constraints, variables
                    opt_client.model = clear_model(opt_client.model)
                    stage_one_opt_run_status = raw_output_dict['stage_one_opt_run_status']

                    if stage_one_reshuffling:
                        if raw_output_dict['stage_one_opt_run_status'] == 'OPTIMAL' and sum(raw_output_dict['truck_selection_dict'].values()) > 1:
                            logger.info("Starting Building and Solving Reshuffling Optimization Model")
                            reshuffling_stage_one_model_construction = ReshufflingStageOneModelConstruction(input_data, opt_client.model, raw_output_dict, output_path)
                            opt_client.model, raw_output_dict = reshuffling_stage_one_model_construction.allocation_model_construction()
                            opt_client.model = clear_model(opt_client.model)
                            stage_one_opt_run_status = raw_output_dict['stage_one_opt_run_status']

                    # Post Processing
                    p = None
                    proposed_po_count = None
                    if raw_output_dict['stage_one_opt_run_status'] == 'OPTIMAL':
                        logger.info("Starting Data Post-Processing")
                        post_process_start_time = time.time()
                        p = PostProcessor(input_data, raw_output_dict, output_path, apo_truck_load_fully_utilized, truck_details_fully_utilized, dc, actual_truck_count)
                        p.results()
                        proposed_po_count = p.proposed_po_count
                        summary_details.append([plan_id, dc, raw_output_dict['optimization_status'], actual_truck_count, len(truck_details_fully_utilized), proposed_po_count, p.actual_lines, p.assign_lines, 0, 'stage_one'])

                        for key, df in p.output_dict.items():
                            if key in finial_output_stage_one:
                                finial_output_stage_one[key].append(df)
                        logger.info("Completed Data Post-Processing in {} seconds".format(round(time.time() - post_process_start_time, 2)))
                    elif raw_output_dict['stage_one_opt_run_status'] == 'INFEASIBLE':
                        logger.warning("Optimization is infeasible")
                        summary_details.append([plan_id, dc, 'INFEASIBLE', actual_truck_count, len(truck_details_fully_utilized), 0, 0, 0, 0, 'stage_one'])
                        # write_IIS_file(output_path, opt_client.model)
                    logger.info(f"Total Program for DC {dc} executed in {round(time.time() - dc_start_time, 2)} seconds")

                    p2 = None
                    stage_two_opt_run_status = None
                    if activate_stage_two:
                        # Stage Two: SO Split Allowed
                        # Data Pre-Processing
                        stage_two_start_time = time.time()
                        logger.info("Starting Stage two Data Pre-Processing")
                        input_data_stage_two = DataHandlingStageTwo(input_data)
                        input_data_stage_two.prepare_model_data()
                        logger.info("Completed Stage two Data Pre-Processing in {} seconds".format(round(time.time() - stage_two_start_time, 2)))

                        # Started Building and Solving Optimization Model
                        logger.info("Starting Stage two Building Optimization Model")
                        model_building_start_time = time.time()
                        model_construction_so_split = OptimizationModelStageTwo(input_data, input_data_stage_two, opt_client.model, output_path, proposed_po_count)
                        opt_client.model, raw_output_stage_two_dict = model_construction_so_split.build_solve_model()
                        logger.info("Completed Building and Solving Optimization Model for Stage two in {} seconds".format(round(time.time() - model_building_start_time, 2)))
                        # Remove all constraints, variables
                        opt_client.model = clear_model(opt_client.model)
                        stage_two_opt_run_status = raw_output_stage_two_dict['stage_two_opt_run_status']

                        if raw_output_stage_two_dict['continue_stage_two'] and stage_two_reshuffling:
                            if stage_two_opt_run_status == 'OPTIMAL' and sum(raw_output_stage_two_dict['truck_selection_dict'].values()) > 1:
                                logger.info("Starting Building and Solving Reshuffling Optimization Model for Stage two")
                                allocation_model_construction_stage_two = ReshufflingStageTwoModelConstruction(input_data_stage_two, opt_client.model, raw_output_stage_two_dict, output_path, proposed_po_count)
                                opt_client.model, raw_output_stage_two_dict = allocation_model_construction_stage_two.allocation_model_construction()
                                stage_two_opt_run_status = raw_output_stage_two_dict['stage_two_opt_run_status']
                                opt_client.model = clear_model(opt_client.model)

                        # Post Processing
                        if raw_output_stage_two_dict['stage_two_opt_run_status'] == 'OPTIMAL':
                            logger.info("Starting Stage two Data Post-Processing")
                            post_process_start_time = time.time()
                            p2 = PostProcessorStageTwo(input_data_stage_two, raw_output_stage_two_dict, output_path, apo_truck_load_fully_utilized, truck_details_fully_utilized, dc, actual_truck_count)
                            p2.results()
                            summary_details.append([plan_id, dc, raw_output_stage_two_dict['optimization_status'], actual_truck_count, len(truck_details_fully_utilized), p2.stage_two_proposed_po_count, p2.actual_lines, p2.assign_lines, p2.orders_splited, 'stage_two'])

                            for key, df in p2.stage_two_output_dict.items():
                                if key in finial_output_stage_two:
                                    finial_output_stage_two[key].append(df)
                            logger.info("Completed Data Post-Processing for Stage two in {} seconds".format(round(time.time() - post_process_start_time, 2)))
                        elif raw_output_stage_two_dict['stage_two_opt_run_status'] == 'INFEASIBLE':
                            logger.warning("Optimization is infeasible")
                            summary_details.append([plan_id, dc, 'INFEASIBLE', actual_truck_count, len(truck_details_fully_utilized), 0, 0, 0, 0, 'stage_two'])
                            # write_IIS_file(output_path, opt_client.model)
                        logger.info(f"Total Program for DC {dc} executed in {round(time.time() - stage_two_start_time, 2)} seconds")

                    if activate_stage_two:
                        if stage_one_opt_run_status == 'OPTIMAL' and stage_two_opt_run_status == 'OPTIMAL':
                            if p2.assign_lines > p.assign_lines: # Anjali K- June3rd 2026- Solver rejcted because of capacity constraints on single line
                                logger.info(f"[STAGE-SELECT] DC={dc}: BRANCH-A → Stage2 wins (S2.assign={p2.assign_lines} > S1.assign={p.assign_lines})")
                                for key, df in p2.stage_two_output_dict.items():
                                    if key in finial_output:
                                        finial_output[key].append(df)
                            elif (p.proposed_po_count <= p2.stage_two_proposed_po_count):
                                logger.info(f"[STAGE-SELECT] DC={dc}: BRANCH-B → Stage1 wins (S1.proposed_po={p.proposed_po_count} <= S2.proposed_po={p2.stage_two_proposed_po_count})")
                                for key, df in p.output_dict.items():
                                    if key in finial_output:
                                        finial_output[key].append(df)
                            else:
                                logger.info(f"[STAGE-SELECT] DC={dc}: BRANCH-C → Stage2 wins (fallback; S1.proposed_po={p.proposed_po_count} > S2.proposed_po={p2.stage_two_proposed_po_count})")
                                for key, df in p2.stage_two_output_dict.items():
                                    if key in finial_output:
                                        finial_output[key].append(df)
                        elif stage_one_opt_run_status == 'OPTIMAL' and stage_two_opt_run_status == 'INFEASIBLE':
                            logger.info(f"[STAGE-SELECT] DC={dc}: BRANCH-D → Stage1 only (S2 INFEASIBLE)")
                            for key, df in p.output_dict.items():
                                if key in finial_output:
                                    finial_output[key].append(df)
                        elif stage_two_opt_run_status == 'OPTIMAL' and stage_one_opt_run_status == 'INFEASIBLE':
                            logger.info(f"[STAGE-SELECT] DC={dc}: BRANCH-E → Stage2 only (S1 INFEASIBLE)")
                            for key, df in p2.stage_two_output_dict.items():
                                if key in finial_output:
                                    finial_output[key].append(df)
                    else:
                        if stage_one_opt_run_status == 'OPTIMAL':
                            for key, df in p.output_dict.items():
                                if key in finial_output:
                                    finial_output[key].append(df)
                else:
                    input_process = InputPostProcessor(dc_input_tables_dict, plan_id, apo_truck_load_fully_utilized, truck_details_fully_utilized, dc)
                    input_process.results()
                    summary_details.append([plan_id, dc, 'NotGoingIntoOptimizer', actual_truck_count,
                                            len(truck_details_fully_utilized), actual_truck_count, input_process.actual_lines, input_process.actual_lines, 0, 'DirectlyFromInput'])
                    for key, df in input_process.output_dict.items():
                        if key in finial_output:
                            finial_output[key].append(df)

            opt_client.model.dispose()

            if len(dc_list) > 0:
                for key, df_lst in finial_output_stage_one.items():
                    if len(df_lst) > 0:
                        df = pd.concat(df_lst)
                    else:
                        df = pd.DataFrame()
                        if key in output_files_col:
                            df = pd.DataFrame(columns=output_files_col[key])
                    file_name = "{}.{}".format(key, 'csv')
                    df.to_csv(os.path.join(str(stage_one_output_path), file_name), index=False)

                if activate_stage_two:
                    for key, df_lst in finial_output_stage_two.items():
                        if len(df_lst) > 0:
                            df = pd.concat(df_lst)
                        else:
                            df = pd.DataFrame()
                            if key in output_files_col:
                                df = pd.DataFrame(columns=output_files_col[key])
                        file_name = "{}.{}".format(key, 'csv')
                        df.to_csv(os.path.join(str(stage_two_output_path), file_name), index=False)

                for key, df_lst in finial_output.items():
                    if len(df_lst) > 0:
                        df = pd.concat(df_lst)
                    else:
                        df = pd.DataFrame()
                        if key in output_files_col:
                            df = pd.DataFrame(columns=output_files_col[key])
                    file_name = "{}.{}".format(key, 'csv')
                    df.to_csv(os.path.join(str(output_path), file_name), index=False)

                summary_df = pd.DataFrame(summary_details, columns=['scenario_id', 'dc', 'status', 'actual_po_count', 'actual_fully_loaded_po_count', 'proposed_po_count', 'actual_lines', 'assign_lines', 'orders_splited', 'stage'])
                summary_df.to_csv(os.path.join(str(output_path), 'summary_df.csv'), index=False)

                # output_file_restructure(output_path)
                ph = PostProcessorAnalysis(input_tables_dict, finial_output, output_path).post_process_analysis()

                # ----- Seam 3 LOCAL: publish final outputs to output_data/ with AERA names -----
                # Mirrors what upload_output() does in AERA mode, but writes to disk only.
                if local_run:
                    os.makedirs(LOCAL_FINAL_OUTPUT_PATH, exist_ok=True)
                    _local_aera_map = {
                        'finial_order_df.csv':      'FINAL_ORDER_OUTPUT.csv',
                        'sel_non_sel_df.csv':       'SELECTED_TRUCK_DF.csv',
                        'output_item.csv':          'SALESORDERITEM_OUTPUT.csv',
                        'output_schedule_line.csv': 'SCHEDULELINE_OUTPUT.csv',
                        'summary_df.csv':           'SUMMARY_OUTPUT.csv',
                    }
                    for _src_name, _dst_name in _local_aera_map.items():
                        _src = os.path.join(output_path, _src_name)
                        _dst = os.path.join(LOCAL_FINAL_OUTPUT_PATH, _dst_name)
                        if os.path.exists(_src):
                            shutil.copy2(_src, _dst)
                            logger.info(f"[LOCAL] Published {_src_name} -> output_data/{_dst_name}")
                        else:
                            logger.warning(f"[LOCAL] Output not found, skipping: {_src_name}")

            # Stop redirecting console logs to logs file
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

            # ----- Seam 3: write-back — skipped in LOCAL mode -----
            if not local_run:
                logger.info("Writeback OutPut Files Process started")
                cortex_sdk_params = {"project_id": project_id}
                dh = DatasetHandling(cortex_sdk_params, workspace=sdk_workspace)
                upload_output(project_id, plan_id, dh, sdk_destination_path, output_path, delimiter, truncate_flag)

                # logger.info("Writeback Log File Process started")
                # upload_logs(project_id, plan_id, dh, sdk_destination_path, logs_path, delimiter, truncate_flag)
                # logger.info("Writeback Log File Process completed")

            logger.info("Total Program executed in {} seconds".format(round(time.time() - program_start_time, 2)))
        response_data = {"optimizer_status": "Pass"}

    except Exception as e:
        project_id = request_data['project_id']
        plan_id = request_data['plan_id']
        delimiter = request_data['delimiter']
        truncate_flag = request_data['truncate_flag']
        sdk_workspace = request_data['sdk_workspace']
        sdk_destination_path = request_data['sdk_destination_path']

        response_data = {"optimizer_status": "Fail"}

        logs_path = os.path.join(BASE_DIR, project_id, 'data', plan_id, 'logs')

        logger.exception(f'Optimization program failed: {e}')
        logger.exception(f"Result: {traceback.format_exc()}")

        # if not local_run:
        #     logger.info("Writeback Log File Process started")
        #     cortex_sdk_params = {"project_id": project_id}
        #     dh = DatasetHandling(cortex_sdk_params, workspace=sdk_workspace)
        #     upload_logs(project_id, plan_id, dh, sdk_destination_path, logs_path, delimiter, truncate_flag)
        #     logger.info("Writeback Log File Process completed")
        raise
    return response_data
# ## Following block should be commented while deploying
# ## Use it, only for testing in a notebook
# def runner():
#     from aera import session
#     aerasdk_session = session.get_session()
#     req = '''{"project_id": "9224D9C4_BEB7_4065_869B_8E3B8F96DB63",
#     "plan_id": "test_anjali_june4_2",
#     "apo_truck_load": "apotruckload",
#     "truck_capacity_details": "truckloadutilization",
#     "dc_slot_schedule": "dcslotschedule",
#     "general_configurations": "generalconfigurations",
#     "delimiter": ",",
#     "truncate_flag": "true",
#     "sdk_workspace": "Logistics TLC",
#     "sdk_destination_path": "Solver_Output"}'''
#     print(handle(req, aerasdk_session=aerasdk_session))
# runner()
