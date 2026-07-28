import time
from src.stage_two.model_building.decision_variables import DecisionVariable
from src.stage_two.model_building.constraints import Constraints
from src.stage_two.model_building.objectives import ModelObjectives
from src.common.logger_config import logger
from src.common import constants
from src.common.utilities import write_lp
import gurobipy
import numpy as np


class OptimizationModelStageTwo:
    def __init__(self, input_data, input_data_stage_two, optimization_model_so_split, output_path, proposed_po_count):
        self.input_data = input_data
        self.model_vars = None
        self.optimization_model_so_split = optimization_model_so_split
        self.input_data_stage_two = input_data_stage_two
        self.output_path = output_path
        self.proposed_po_count = proposed_po_count

        logger.info("Stage Two Build and Solve Optimization Model")
        self.model_vars = DecisionVariable(self.optimization_model_so_split, self.input_data_stage_two)
        self.model_constraints = Constraints(self.optimization_model_so_split, self.model_vars, self.input_data_stage_two)
        self.model_objectives = ModelObjectives(self.optimization_model_so_split, self.model_vars, self.output_path, constants.objective_type_stage_two, constants.objectives_stage_two, constants.objective_sense_stage_two)

    def build_solve_model(self):

        logger.info("Starting Stage two Building Optimization Model")
        model_building_start_time = time.time()

        logger.info("Stage two Creating Variables")
        variable_creating_start_time = time.time()
        self.model_vars.create_decision_variables()
        logger.info("Completed Creating Stage two Variables in {} seconds".format(round(time.time() - variable_creating_start_time, 2)))

        logger.info("Stage two Creating Constraints")
        constraints_creation_start_time = time.time()
        self.model_constraints.create_constraints()
        logger.info("Completed Creating Stage two Constraints in {} seconds".format(round(time.time() - constraints_creation_start_time, 2)))

        if not constants.manual_hierarchical_stage_two:
            logger.info("Stage two Creating Objective Function")
            objective_creation_start_time = time.time()
            self.model_objectives.create_model_objective()
            logger.info("Completed Creating Stage two Objective in {} seconds".format(round(time.time() - objective_creation_start_time, 2)))

            logger.info("Completed Building Optimization Model for Stage two in {} seconds".format(round(time.time() - model_building_start_time, 2)))

            # Writing Lp File
            if constants.lp_file:
                lp_start_time = time.time()
                write_lp(self.output_path, self.optimization_model_so_split)
                logger.info("Completed Writing LP File for Stage two in {} seconds".format(round(time.time() - lp_start_time, 2)))
            else:
                logger.info("Skipped Writing LP File for Stage two")

            # Solving Optimization Model
            logger.info("Solving Stage two Optimization Model")
            solve_start_time = time.time()
            self.optimization_model_so_split.optimize()
            logger.info("Completed Solving Stage two Model in {} seconds".format(round(time.time() - solve_start_time, 2)))
        else:
            self.optimization_model_so_split = self.model_objectives.create_manual_hierarchical_objectives(po_count=self.proposed_po_count, updated_truck_selection_combinations =self.input_data_stage_two.updated_truck_selection_combinations)

        raw_output_dict = dict()
        if self.optimization_model_so_split.status in [gurobipy.GRB.OPTIMAL, gurobipy.GRB.TIME_LIMIT, gurobipy.GRB.INTERRUPTED]:
            logger.info(f"Optimization Status {constants.optimization_status[self.optimization_model_so_split.status]}")
            logger.info("Optimization is done with ObjectiveValue: " + str(self.optimization_model_so_split.objVal))

            kpi_dict = {}
            for key in self.model_vars.global_var:
                kpi_dict[key] = self.model_vars.global_var[key].x

            order_allocation_dict = {}
            for key in self.model_vars.order_allocation_var:
                order_allocation_dict[key] = np.round(self.model_vars.order_allocation_var[key].x)

            truck_selection_dict = {}
            selected_truck_count = 0
            for key in self.model_vars.truck_selection_var:
                truck_selection_dict[key] = np.round(self.model_vars.truck_selection_var[key].x)
                selected_truck_count += np.round(self.model_vars.truck_selection_var[key].x)

            continue_stage_two = True
            if self.proposed_po_count is not None:
                if selected_truck_count >= self.proposed_po_count:
                    continue_stage_two = False

            # Extract order_non_selection_var values (solver rejected lines)
            order_non_selection_dict = {}
            if constants.order_slack_flag_stage_two and self.model_vars.order_non_selection_var:
                for key in self.model_vars.order_non_selection_var:
                    order_non_selection_dict[key] = np.round(self.model_vars.order_non_selection_var[key].x)

            raw_output_dict['kpi_dict'] = kpi_dict
            raw_output_dict['order_allocation_dict'] = order_allocation_dict
            raw_output_dict['truck_selection_dict'] = truck_selection_dict
            raw_output_dict['order_non_selection_dict'] = order_non_selection_dict
            raw_output_dict['stage_two_opt_run_status'] = 'OPTIMAL'
            raw_output_dict['continue_stage_two'] = continue_stage_two
            raw_output_dict['optimization_status'] = constants.optimization_status[self.optimization_model_so_split.status]

        else:
            raw_output_dict['kpi_dict'] = {}
            raw_output_dict['order_allocation_dict'] = {}
            raw_output_dict['truck_selection_dict'] = {}
            raw_output_dict['order_non_selection_dict'] = {}
            raw_output_dict['stage_two_opt_run_status'] = 'INFEASIBLE'
            raw_output_dict['continue_stage_two'] = False
            raw_output_dict['optimization_status'] = 'INFEASIBLE'

        return self.optimization_model_so_split, raw_output_dict
