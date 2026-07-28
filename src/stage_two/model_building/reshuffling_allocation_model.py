import time
from src.stage_two.model_building.decision_variables import ReshufflingStageTwoDecisionVariable
from src.stage_two.model_building.constraints import ReshufflingStageTwoConstraints
from src.stage_two.model_building.objectives import ModelObjectives
from src.common.logger_config import logger
from src.common import constants
from src.common.utilities import write_lp
import gurobipy
from src.common.utils import find_valid_period


def process_previous_output(raw_output_dict):
    order_var_dict = {}
    order_sel_lst = set()
    sel_po_period_lst = set()
    sel_period_lst = set()
    selected_order_dict = {}
    for key, values in raw_output_dict['order_allocation_dict'].items():
        sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
        order_var_dict[key] = 0
        if values >= 1:
            order_sel_lst.add((sales_document, sales_document_item, schedule_line, material, po_number, r_type))
            selected_order_dict[key] = values
            sel_po_period_lst.add((po, period))
            sel_period_lst.add(period)
    return order_var_dict, order_sel_lst, sel_po_period_lst, sel_period_lst, selected_order_dict

def process_data_preprocessing(input_data_stage_two, order_sel_lst, sel_po_period_lst, sel_period_lst):
    updated_order_allocation_combinations = {}
    for order_key in order_sel_lst:
        sales_document, sales_document_item, schedule_line, material, po_number, r_type = order_key
        ord_details = input_data_stage_two.updated_apo_truck_load_dict[po_number][(sales_document, sales_document_item, schedule_line, material, r_type)]
        if ord_details['priority_line_flag'] == 'Y':
            if ord_details['requested_delivery_period'] <= ord_details['delivery_period']:
                period_lst = []
                result = find_valid_period(ord_details['delivery_period'], input_data_stage_two.input_data.horizon, input_data_stage_two.input_data.period_day_name_mapping, input_data_stage_two.input_data.dc_slot_schedule_dict)
                if result is not None:
                    period_lst.append(result)
            else:
                period_lst = []
                # Try within requested window
                for period in range(ord_details['delivery_period'], ord_details['requested_delivery_period'] + 1):
                    day_name = input_data_stage_two.input_data.period_day_name_mapping[period]['day_name']
                    if input_data_stage_two.input_data.dc_slot_schedule_dict.get(day_name, 0) > 0:
                        period_lst.append(period)

                # If nothing found, fallback after requested
                if not period_lst:
                    result = find_valid_period(ord_details['requested_delivery_period'], input_data_stage_two.input_data.horizon, input_data_stage_two.input_data.period_day_name_mapping, input_data_stage_two.input_data.dc_slot_schedule_dict)
                    if result is not None:
                        period_lst.append(result)
        else:
            period_lst = list(sel_period_lst)
        for (po, period) in sel_po_period_lst:
            if period >= ord_details['delivery_period'] and period in period_lst:
                updated_order_allocation_combinations[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)] = ord_details
    logger.info("Order Allocation Combinations Created")

    updated_truck_selection_combinations = {}
    updated_order_truck_mapping = {}
    updated_order_selection_mapping_dict = {}
    updated_shuffle_together_mapping_dict = {}
    updated_shuffle_order_schedule_line_mapping_dict = {}
    for key, values in updated_order_allocation_combinations.items():
        sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
        if (po, period) not in updated_truck_selection_combinations:
            updated_truck_selection_combinations[(po, period)] = []
        updated_truck_selection_combinations[(po, period)].append(key)

        if (sales_document, sales_document_item, schedule_line, material, po_number) not in updated_order_truck_mapping:
            updated_order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)] = {}
        if r_type not in updated_order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)]:
            updated_order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)][r_type] = set()
        updated_order_truck_mapping[(sales_document, sales_document_item, schedule_line, material, po_number)][r_type].add((po, period))

        if (sales_document, sales_document_item, material, po_number) not in updated_order_selection_mapping_dict:
            updated_order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)] = {}
        if (po, period) not in updated_order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)]:
            updated_order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)] = set()
        updated_order_selection_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)].add((schedule_line, r_type))

        if values['shuffle_together_flag'] == 'Y':
            if (sales_document, sales_document_item, material, po_number) not in updated_shuffle_together_mapping_dict:
                updated_shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)] = {}
            if (po, period) not in updated_shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)]:
                updated_shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)] = set()
            updated_shuffle_together_mapping_dict[(sales_document, sales_document_item, material, po_number)][(po, period)].add((schedule_line, r_type))

            if (sales_document, sales_document_item, material, po_number) not in updated_shuffle_order_schedule_line_mapping_dict:
                updated_shuffle_order_schedule_line_mapping_dict[(sales_document, sales_document_item, material, po_number)] = set()
            updated_shuffle_order_schedule_line_mapping_dict[(sales_document, sales_document_item, material, po_number)].add((schedule_line, r_type))


    return updated_order_allocation_combinations, updated_truck_selection_combinations, updated_order_truck_mapping, updated_order_selection_mapping_dict, updated_shuffle_together_mapping_dict, updated_shuffle_order_schedule_line_mapping_dict



class ReshufflingStageTwoModelConstruction:

    def __init__(self, input_data_stage_two, optimization_model, raw_output_dict, output_path, proposed_po_count):
        self.input_data_stage_two = input_data_stage_two
        self.optimization_model = optimization_model
        self.output_path = output_path
        self.raw_output_dict = raw_output_dict
        self.proposed_po_count = proposed_po_count

    def allocation_model_construction(self):
        # Previous Output
        order_var_dict, order_sel_lst, sel_po_period_lst, sel_period_lst, selected_order_dict = process_previous_output(self.raw_output_dict)

        # Data Pre Processing
        updated_order_allocation_combinations, updated_truck_selection_combinations, updated_order_truck_mapping, updated_order_selection_mapping_dict, updated_shuffle_together_mapping_dict, updated_shuffle_order_schedule_line_mapping_dict = process_data_preprocessing(self.input_data_stage_two, order_sel_lst, sel_po_period_lst, sel_period_lst)

        # Model Build and Solve
        logger.info("Build and Solve Optimization Model")
        alloc_model_vars = ReshufflingStageTwoDecisionVariable(self.optimization_model, updated_order_allocation_combinations, updated_truck_selection_combinations, updated_order_truck_mapping, selected_order_dict, updated_order_selection_mapping_dict, self.input_data_stage_two)
        alloc_model_constraints = ReshufflingStageTwoConstraints(self.optimization_model, alloc_model_vars, self.input_data_stage_two,updated_order_allocation_combinations, updated_order_truck_mapping, updated_truck_selection_combinations, updated_order_selection_mapping_dict, updated_shuffle_together_mapping_dict, updated_shuffle_order_schedule_line_mapping_dict)
        alloc_model_objectives = ModelObjectives(self.optimization_model, alloc_model_vars, self.output_path, constants.stage_two_reshuffling_objective_type, constants.stage_two_reshuffling_objectives, constants.stage_two_reshuffling_objective_sense)
        logger.info("Starting Building Optimization Model")
        model_building_start_time = time.time()

        logger.info("Creating Variables")
        variable_creating_start_time = time.time()
        alloc_model_vars.create_allocation_decision_variables()
        logger.info("Completed Creating Variables in {} seconds".format(round(time.time() - variable_creating_start_time, 2)))

        logger.info("Creating Constraints")
        constraints_creation_start_time = time.time()
        alloc_model_constraints.create_allocation_constraints()
        logger.info("Completed Creating Constraints in {} seconds".format(round(time.time() - constraints_creation_start_time, 2)))

        if not constants.stage_two_reshuffling_manual_hierarchical:
            logger.info("Creating Objective Function")
            objective_creation_start_time = time.time()
            alloc_model_objectives.create_model_objective()
            logger.info("Completed Creating Objective in {} seconds".format(round(time.time() - objective_creation_start_time, 2)))
            logger.info("Completed Building Optimization Model in {} seconds".format(round(time.time() - model_building_start_time, 2)))

            # Writing Lp File
            if constants.lp_file:
                lp_start_time = time.time()
                write_lp(self.output_path, self.optimization_model)
                logger.info("Completed Writing LP File in {} seconds".format(round(time.time() - lp_start_time, 2)))
            else:
                logger.info("Skipped Writing LP File")

            # Solving Optimization Model
            logger.info("Solving Optimization Model")
            solve_start_time = time.time()
            self.optimization_model.optimize()
            logger.info("Completed Solving Model in {} seconds".format(round(time.time() - solve_start_time, 2)))

        else:
            self.optimization_model = alloc_model_objectives.create_manual_hierarchical_objectives(po_count=self.proposed_po_count, updated_truck_selection_combinations =updated_truck_selection_combinations)

        raw_allocation_output_dict = dict()
        if self.optimization_model.status in [gurobipy.GRB.OPTIMAL, gurobipy.GRB.TIME_LIMIT, gurobipy.GRB.INTERRUPTED]:
            kpi_dict = {}
            for key in alloc_model_vars.global_var:
                kpi_dict[key] = alloc_model_vars.global_var[key].x

            self.raw_output_dict['kpi_dict'].update(kpi_dict)

            for key in alloc_model_vars.order_allocation_var:
                if key in order_var_dict.keys():
                    order_var_dict[key] = alloc_model_vars.order_allocation_var[key].x

            raw_allocation_output_dict['kpi_dict'] = self.raw_output_dict['kpi_dict']
            raw_allocation_output_dict['order_allocation_dict'] = order_var_dict
            raw_allocation_output_dict['truck_selection_dict'] = self.raw_output_dict['truck_selection_dict']
            raw_allocation_output_dict['order_non_selection_dict'] = self.raw_output_dict.get('order_non_selection_dict', {})
            raw_allocation_output_dict['stage_two_opt_run_status'] = 'OPTIMAL'
            raw_allocation_output_dict['optimization_status'] = constants.optimization_status[self.optimization_model.status]
        else:
            raw_allocation_output_dict['kpi_dict'] = {}
            raw_allocation_output_dict['order_allocation_dict'] = {}
            raw_allocation_output_dict['truck_selection_dict'] = {}
            raw_allocation_output_dict['order_non_selection_dict'] = {}
            raw_allocation_output_dict['stage_two_opt_run_status'] = 'INFEASIBLE'
            raw_allocation_output_dict['optimization_status'] = 'INFEASIBLE'
        return self.optimization_model, raw_allocation_output_dict















