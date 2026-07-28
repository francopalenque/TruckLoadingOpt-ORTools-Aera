from gurobipy import GRB, LinExpr
from src.common.logger_config import logger
from src.common.constants import lp_file
import time
from src.common.utilities import write_lp

class ModelObjectives:

    def __init__(self, model, model_vars, input_data, output_path, objective_type, objectives, objective_sense):

        self.model = model
        self.model_vars = model_vars
        self.input_data = input_data
        self.output_path = output_path
        self.objective_type = objective_type
        self.objectives = objectives
        self.objective_sense = GRB.MAXIMIZE if objective_sense == 'Maximization' else GRB.MINIMIZE

    def create_model_objective(self):
        if self.objective_type == 'Blended':
            self.create_blended_objectives()
        elif self.objective_type == 'Hierarchical':
            self.create_hierarchical_objectives()

    def create_blended_objectives(self):
        global_variables = self.model_vars.global_var
        expression = LinExpr()

        for key, value in self.objectives.items():
            expression.add(value['weight'] * global_variables[key])

        self.model.setObjective(expression, self.objective_sense)
        logger.info("Blended Objective Function Created")

    def create_hierarchical_objectives(self):
        global_variables = self.model_vars.global_var
        objective_expression_dict = dict()

        for key, value in self.objectives.items():
            if value['priority'] not in objective_expression_dict:
                objective_expression_dict.update({value['priority']: LinExpr()})
            objective_expression_dict[value['priority']].add(global_variables[key])

        objective_expression_dict = dict(sorted(objective_expression_dict.items(),reverse=True))
        index = 0
        for priority in objective_expression_dict:
            self.model.setObjectiveN(objective_expression_dict[priority], priority=priority, weight=1,index=index, name="Priority " + str(priority))
            index += 1
        self.model.modelSense = self.objective_sense

        logger.info("Hierarchical Objective Function Created")

    def create_manual_hierarchical_objectives(self):
        objective_expression_dict = {}
        prio_obj_name = {}
        logger.info("Creating Objective Function")
        for key, value in self.objectives.items():
            if value['priority'] not in objective_expression_dict:
                objective_expression_dict.update({value['priority']: LinExpr()})
            objective_expression_dict[value['priority']].add(self.model_vars.global_var[key] * value['weight'])
            if value['priority'] not in prio_obj_name:
                prio_obj_name.update({value['priority']: []})
            prio_obj_name[value['priority']].append(key)

        objective_expression_dict = dict(sorted(objective_expression_dict.items(), reverse=True))
        for priority, expression in objective_expression_dict.items():
            self.model.setObjective(expression, self.objective_sense)
            logger.info(f"Completed Building Optimization Model for priority {priority} with {prio_obj_name[priority]}")

            # Writing Lp File
            if lp_file:
                lp_start_time = time.time()
                write_lp(self.output_path, self.model)
                logger.info("Completed Writing LP File in {} seconds".format(round(time.time() - lp_start_time, 2)))
            else:
                logger.info("Skipped Writing LP File")

            # Solving Optimization Model
            logger.info("Solving Optimization Model")
            solve_start_time = time.time()
            self.model.optimize()
            logger.info("Completed Solving Model in {} seconds".format(round(time.time() - solve_start_time, 2)))

            try:
                if self.model.status in [GRB.OPTIMAL,GRB.TIME_LIMIT, GRB.INTERRUPTED]:
                    obj_val = self.model.objVal
                    if self.objective_sense == 'Maximization':
                        self.model.addConstr(expression >= obj_val * (1 - 1e-4), name=f"ct_{'_'.join(prio_obj_name[priority])}")
                    else:
                        self.model.addConstr(expression <= obj_val * (1 + 1e-4),name=f"ct_{'_'.join(prio_obj_name[priority])}")
                elif self.model.status in [GRB.INFEASIBLE]:
                    break
            except:
                logger.info(f"Objective value not found for priority {priority}, setting to 0")

        return self.model


