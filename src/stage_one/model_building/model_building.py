import time
from src.stage_one.model_building.decision_variables import DecisionVariable
from src.stage_one.model_building.constraints import Constraints
from src.stage_one.model_building.objectives import ModelObjectives
from src.common.logger_config import logger
from src.common import constants
from src.common.utilities import write_lp
import gurobipy
import numpy as np


class OptimizationModel:
    def __init__(self, input_data, optimization_model, output_path):
        self.input_data = input_data
        self.model_vars = None
        self.optimization_model = optimization_model
        self.output_path = output_path

        logger.info("Build and Solve Optimization Model")

        self.model_vars = DecisionVariable(self.optimization_model, self.input_data)
        self.model_constraints = Constraints(self.optimization_model, self.model_vars, self.input_data)
        self.model_objectives = ModelObjectives(self.optimization_model, self.model_vars, self.input_data, self.output_path, constants.objective_type, constants.objectives, constants.objective_sense)

    def build_solve_model(self):

        logger.info("Starting Building Optimization Model")
        model_building_start_time = time.time()

        logger.info("Creating Variables")
        variable_creating_start_time = time.time()
        self.model_vars.create_decision_variables()
        logger.info("Completed Creating Variables in {} seconds".format(round(time.time() - variable_creating_start_time, 2)))

        logger.info("Creating Constraints")
        constraints_creation_start_time = time.time()
        self.model_constraints.create_constraints()
        logger.info("Completed Creating Constraints in {} seconds".format(round(time.time() - constraints_creation_start_time, 2)))

        if not constants.manual_hierarchical:
            logger.info("Creating Objective Function")
            objective_creation_start_time = time.time()
            self.model_objectives.create_model_objective()
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
            self.optimization_model = self.model_objectives.create_manual_hierarchical_objectives()

        raw_output_dict = dict()
        if self.optimization_model.status in [gurobipy.GRB.OPTIMAL, gurobipy.GRB.TIME_LIMIT, gurobipy.GRB.INTERRUPTED]:
            logger.info(f"Optimization Status {constants.optimization_status[self.optimization_model.status]}")
            logger.info("Optimization is done with ObjectiveValue: " + str(self.optimization_model.objVal))

            kpi_dict = {}
            for key in self.model_vars.global_var:
                kpi_dict[key] = self.model_vars.global_var[key].x

            order_allocation_dict = {}
            for key in self.model_vars.order_allocation_var:
                order_allocation_dict[key] = np.round(self.model_vars.order_allocation_var[key].x)

            truck_selection_dict = {}
            for key in self.model_vars.truck_selection_var:
                truck_selection_dict[key] = np.round(self.model_vars.truck_selection_var[key].x)

            # Extract order_non_selection_var values (solver rejected lines)
            order_non_selection_dict = {}
            if constants.order_slack_flag and self.model_vars.order_non_selection_var:
                for key in self.model_vars.order_non_selection_var:
                    order_non_selection_dict[key] = np.round(self.model_vars.order_non_selection_var[key].x)

            raw_output_dict['kpi_dict'] = kpi_dict
            raw_output_dict['order_allocation_dict'] = order_allocation_dict
            raw_output_dict['truck_selection_dict'] = truck_selection_dict
            raw_output_dict['order_non_selection_dict'] = order_non_selection_dict
            raw_output_dict['stage_one_opt_run_status'] = 'OPTIMAL'
            raw_output_dict['optimization_status'] = constants.optimization_status[self.optimization_model.status]
        else:
            raw_output_dict['kpi_dict'] = {}
            raw_output_dict['order_allocation_dict'] = {}
            raw_output_dict['truck_selection_dict'] = {}
            raw_output_dict['order_non_selection_dict'] = {}
            raw_output_dict['stage_one_opt_run_status'] = 'INFEASIBLE'
            raw_output_dict['optimization_status'] = 'INFEASIBLE'

        return self.optimization_model, raw_output_dict
