from gurobipy import LinExpr, min_
from src.common.logger_config import logger
from src.common.constants import (order_in_original_truck_slack_stage_two, order_split_flag, order_slack_flag_stage_two,
                                  stage_two_truck_count_not_within_range, stage_two_truck_unused_cost, order_in_original_truck_constraint_stage_two)
import math


class Constraints:
    def __init__(self, model, model_variables, input_data_stage_two):
        self.model = model
        self.model_vars = model_variables
        self.input_data_stage_two = input_data_stage_two

    def create_constraints(self):
        # Constraints
        self.create_only_one_time_selection_constraint()
        self.create_weight_capacity_constraints()
        self.create_volume_capacity_constraints()
        self.create_pallet_capacity_constraints()
        self.create_truck_period_limitation_constraints()
        self.create_truck_only_one_time_selection_over_period_constraints()
        if order_in_original_truck_constraint_stage_two:
            self.create_order_in_original_truck_constraints()
        self.create_order_schedule_line_mapping_constraints()
        self.create_shuffle_together_balancing_constraints()
        if order_split_flag:
            self.create_order_split_count_constraints()

        # Objectives
        self.create_total_truck_count_cost_objective()
        self.create_total_truck_selection_preference_cost_objective()
        self.create_total_truck_period_delay_cost_objective()
        self.create_total_order_item_selection_cost_objective()
        if order_in_original_truck_slack_stage_two:
            self.create_total_order_not_in_original_truck_cost_objective()
        if order_split_flag:
            self.create_total_order_splits_cost_objective()
        if order_slack_flag_stage_two:
            self.create_total_order_selection_cost_objective()


    # Constraints
    def create_only_one_time_selection_constraint(self):
        expr = LinExpr()
        for key, po_details in self.input_data_stage_two.updated_order_truck_mapping.items():
            sales_document, sales_document_item, schedule_line, material, po_number = key
            for r_type, po_list in po_details.items():
                name_key = [str(x) for x in (sales_document, sales_document_item, schedule_line, material, po_number, r_type)]
                ct_name = "Order_Only_One_Time_Selection" + "|" + '|'.join(name_key)
                if r_type == 'integer':
                    for (po, period) in po_list:
                        expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
                    rhs = self.input_data_stage_two.updated_apo_truck_load_dict[po_number][sales_document, sales_document_item, schedule_line, material, r_type]['pallet_spot']
                    slk = 0
                    if order_slack_flag_stage_two:
                        if (sales_document, sales_document_item, schedule_line, material, po_number, r_type) in self.model_vars.order_non_selection_var:
                            slk = self.model_vars.order_non_selection_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type)]
                    self.model.addConstr(expr == rhs-slk, ct_name)
                    expr.clear()
                elif r_type == 'decimal':
                    for (po, period) in po_list:
                        expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
                    slk = 0
                    if order_slack_flag_stage_two:
                        if (sales_document, sales_document_item, schedule_line, material, po_number,r_type) in self.model_vars.order_non_selection_var:
                            slk = self.model_vars.order_non_selection_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type)]
                    self.model.addConstr(expr == 1-slk, ct_name)
                    expr.clear()
        logger.info("Created Order Only One Time Selection Constraints")

    def create_weight_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.input_data_stage_two.updated_truck_selection_combinations.items():
            weight_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['weight_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                weight = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['weight_per_pallet'], 6)
                expr.add(self.model_vars.order_allocation_var[key],weight)
            name_key = [str(x) for x in (po, period)]
            ct_name = "Weight_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(expr <= self.model_vars.truck_selection_var[(po, period)] * weight_limit, ct_name)
            expr.clear()
        logger.info("Created Weight Capacity Constraints")

    def create_volume_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.input_data_stage_two.updated_truck_selection_combinations.items():
            volume_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['volume_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                volume = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['volume_per_pallet'], 6)
                expr.add(self.model_vars.order_allocation_var[key], volume)
            name_key = [str(x) for x in (po, period)]
            ct_name = "Volume_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(expr <= self.model_vars.truck_selection_var[(po, period)] * volume_limit, ct_name)
            expr.clear()
        logger.info("Created Volume Capacity Constraints")

    def create_pallet_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.input_data_stage_two.updated_truck_selection_combinations.items():
            pallet_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['pallet_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
                if r_type == 'integer':
                    expr.add(self.model_vars.order_allocation_var[key])
                elif r_type == 'decimal':
                    pallet = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['pallet_spot'], 6)
                    expr.add(self.model_vars.order_allocation_var[key], pallet)
            name_key = [str(x) for x in (po, period)]
            ct_name = "Pallet_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(expr <= self.model_vars.truck_selection_var[(po, period)] * pallet_limit, ct_name)
            expr.clear()
        logger.info("Created Pallet Capacity Constraints")

    def create_truck_period_limitation_constraints(self):
        expr = LinExpr()
        for period, po_list in self.input_data_stage_two.updated_period_truck_mapping.items():
            for po in po_list:
                expr.add(self.model_vars.truck_selection_var[(po, period)], 1)

            if self.input_data_stage_two.input_data.period_day_name_mapping[period]['day_name'] in self.input_data_stage_two.input_data.dc_slot_schedule_dict:
                avail_slots = self.input_data_stage_two.input_data.dc_slot_schedule_dict[self.input_data_stage_two.input_data.period_day_name_mapping[period]['day_name']]
            else:
                avail_slots = 0
            name_key = [str(x) for x in (period,)]
            ct_name = "Truck_Period_Limitation" + "|" + '|'.join(name_key)
            self.model.addConstr(expr<=avail_slots, ct_name)
            expr.clear()
        logger.info("Created Truck Period Limitation Constraints")

    def create_truck_only_one_time_selection_over_period_constraints(self):
        expr = LinExpr()
        for po, period_list in self.input_data_stage_two.updated_truck_period_mapping.items():
            for period in period_list:
                expr.add(self.model_vars.truck_selection_var[(po, period)], 1)
            name_key = [str(x) for x in (po,)]
            ct_name = "Truck_Only_One_Time_Selection_" + "|" + '|'.join(name_key)
            self.model.addConstr(expr<=1, ct_name)
            expr.clear()
        logger.info("Created Truck Only One Time Selectio over Periods Constraints")

    def create_order_in_original_truck_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.input_data_stage_two.updated_original_truck_order_mapping.items():
            order_count = 0
            for order_key in order_list:
                sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = order_key
                expr.add(self.model_vars.order_allocation_var[order_key], 1)
                if r_type == 'integer':
                    order_count += self.input_data_stage_two.updated_order_allocation_combinations[order_key]['pallet_spot']
                elif r_type == 'decimal':
                    order_count += 1
            name_key = [str(x) for x in (po,period)]
            ct_name = "ct_original_order_in_same_truck_mapping_" + "|" + '|'.join(name_key)
            slk = 0
            if order_in_original_truck_slack_stage_two:
                if (po, period) in  self.model_vars.order_in_original_truck_slack_var:
                    slk = self.model_vars.order_in_original_truck_slack_var[(po, period)]
            self.model.addConstr(expr==(self.model_vars.truck_selection_var[(po, period)] * order_count) - slk, ct_name)
            expr.clear()
        logger.info("Created Order in Original Truck Constraints")

    def create_order_split_count_constraints(self):
        expr = LinExpr()
        for key, po_details in self.model_vars.order_split_count_dict.items():
            sales_document, sales_document_item, schedule_line, material, po_number, po = key
            mul = self.input_data_stage_two.input_data.apo_truck_load_dict[po_number][(sales_document, sales_document_item, schedule_line, material)]['pallet_spot'] +10
            order_split_count = self.model_vars.order_split_count_var[key]
            for r_type, period_list in po_details.items():
                for period in period_list:
                    expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
            ct_name = "ct_Order_Split_Count_" + "|" + '|'.join(key)
            self.model.addConstr(expr <= order_split_count * mul,name=ct_name)
            expr.clear()
        logger.info("Created Order Split Count Constraints")

    def create_order_schedule_line_mapping_constraints(self):

        expr_selection = LinExpr()
        expr_mapping = LinExpr()
        for key, po_details in self.input_data_stage_two.updated_order_selection_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            for (po, period), schedule_line_lst in po_details.items():
                order_item_sel_var = self.model_vars.order_item_selection_var[(sales_document, sales_document_item, material, po_number, po, period)]
                expr_selection.add(order_item_sel_var, 1)
                coef = 0
                for (schedule_line, r_type) in schedule_line_lst:
                    order_allocation_var = self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)]
                    if r_type == 'integer':
                        coef += self.input_data_stage_two.updated_order_allocation_combinations[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)]['pallet_spot']
                    else:
                        coef += 1
                    expr_mapping.add(order_allocation_var, 1)

                name_key = [str(x) for x in (sales_document, sales_document_item, material, po_number, po, period)]
                ct_name = "Order_Selection_Mapping" + "|" + '|'.join(name_key)
                self.model.addConstr(expr_mapping <= order_item_sel_var * coef, name=ct_name)
                expr_mapping.clear()

            name_key = [str(x) for x in key]
            ct_name = "Order_Selection" + "|" + '|'.join(name_key)
            self.model.addConstr(expr_selection <= self.input_data_stage_two.input_data.model_parameters['max_trucks_per_order_item'] + self.model_vars.order_item_selection_slack_var[key], name=ct_name)
            expr_selection.clear()
        logger.info("Created Order Selection Mapping Constraints")

    def create_shuffle_together_balancing_constraints(self):

        for key, schedule_line_lst in self.input_data_stage_two.updated_shuffle_order_schedule_line_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            # Choose one "anchor" order in each group
            anchor_schedule_line = list(schedule_line_lst)[0]
            # Enforce all others in the group take same truck as anchor
            for (po, period) in self.input_data_stage_two.updated_shuffle_together_mapping_dict[key]:
                if schedule_line_lst == self.input_data_stage_two.updated_shuffle_together_mapping_dict[key][(po, period)]:
                    for (sch_lne, r_typ) in list(schedule_line_lst)[1:]:
                        anchor_order_key = (sales_document, sales_document_item, anchor_schedule_line[0], material, po_number, r_typ, po, period)
                        mapping_order_key = (sales_document, sales_document_item, sch_lne, material, po_number, r_typ, po, period)
                        name_key = [str(x) for x in mapping_order_key]
                        ct_name = "Order_Shuffle_Together" + "|" + '|'.join(name_key)
                        self.model.addConstr(self.model_vars.order_allocation_var[mapping_order_key] ==
                                             self.model_vars.order_allocation_var[anchor_order_key], name=ct_name)
                else:
                    for (sch_lne, r_typ) in self.input_data_stage_two.updated_shuffle_together_mapping_dict[key][(po, period)]:
                        self.model_vars.order_allocation_var[(sales_document, sales_document_item, sch_lne, material, po_number, r_typ, po, period)].ub = 0

        logger.info("Created Shuffle Together Mapping Constraints")


    # Objectives
    def create_total_truck_count_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.truck_selection_var.keys():
            expr.add(self.model_vars.truck_selection_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_TRUCK_COUNT'], -1)
        ct_name = "ct_total_truck_selection"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Selection Constraints")

    def create_total_truck_selection_preference_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.truck_selection_var.keys():
            po, period = key
            cost = self.input_data_stage_two.input_data.truck_po_level_details[po]['under_utilization_cost'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 100
            if math.isnan(cost):
                cost = 100
            expr.add(self.model_vars.truck_selection_var[key], cost+1)
        expr.add(self.model_vars.global_var['TOTAL_TRUCK_SELECTION_PREFERENCE'], -1)
        ct_name = "ct_total_truck_selection_preference"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Selection Preference Constraints")

    def create_total_truck_period_delay_cost_objective(self):
        expr = LinExpr()
        for po, values in self.input_data_stage_two.input_data.truck_po_level_details.items():
            requested_delivery_period = values['requested_delivery_period']
            if po in self.input_data_stage_two.updated_truck_period_mapping:
                for period in self.input_data_stage_two.updated_truck_period_mapping[po]:
                    if period > requested_delivery_period:
                        expr.add(self.model_vars.truck_selection_var[(po, period)], (period-requested_delivery_period)+2)
                    elif period < requested_delivery_period:
                        expr.add(self.model_vars.truck_selection_var[(po, period)],(requested_delivery_period-period)+1)
                    else:
                        expr.add(self.model_vars.truck_selection_var[(po, period)],0)
        expr.add(self.model_vars.global_var['TOTAL_TRUCK_DELAY_ADVANCE_COST'], -1)
        ct_name = "ct_total_truck_delay_advance_cost"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Delay and Advance Cost Constraints")

    def create_total_order_not_in_original_truck_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_in_original_truck_slack_var.keys():
            expr.add(self.model_vars.order_in_original_truck_slack_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST'], -1)
        ct_name = "ct_total_order_not_in_original_truck"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order Not In Original Truck Constraints")

    def create_total_order_splits_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_split_count_var.keys():
            sales_document, sales_document_item, schedule_line, material, po_number, po = key
            if po_number != po:
                expr.add(self.model_vars.order_split_count_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_SPLIT_COST'], -1)
        ct_name = "ct_total_order_split_cost"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order Split Cost Constraints")

    def create_total_order_selection_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_non_selection_var.keys():
            sales_document, sales_document_item, schedule_line, material, po_number, r_type = key
            cost = 1
            if po_number in self.input_data_stage_two.updated_apo_truck_load_dict and (sales_document, sales_document_item, schedule_line, material, r_type) in self.input_data_stage_two.updated_apo_truck_load_dict[po_number]:
                if self.input_data_stage_two.updated_apo_truck_load_dict[po_number][(sales_document, sales_document_item, schedule_line, material, r_type)]['priority_line_flag'] == 'Y':
                    cost = 100
            expr.add(self.model_vars.order_non_selection_var[key], cost)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_SLACK'], -1)
        ct_name = "ct_total_order_selection_slack"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Selection Constraints")

    def create_total_order_item_selection_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_item_selection_slack_var.keys():
            sales_document, sales_document_item, material, po_number = key
            cost = 1
            expr.add(self.model_vars.order_item_selection_slack_var[key], cost)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_ITEM_SELECTION_SLACK'], -1)
        ct_name = "ct_total_order_item_selection_slack"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order Item Selection Constraints")


class ReshufflingStageTwoConstraints:
    def __init__(self,model,model_variables,input_data_stage_two,updated_order_allocation_combinations, updated_order_truck_mapping, updated_truck_selection_combinations,
                 updated_order_selection_mapping_dict, updated_shuffle_together_mapping_dict, updated_shuffle_order_schedule_line_mapping_dict):
        self.model = model
        self.model_vars = model_variables
        self.input_data_stage_two = input_data_stage_two
        self.updated_order_allocation_combinations = updated_order_allocation_combinations
        self.updated_order_truck_mapping = updated_order_truck_mapping
        self.updated_truck_selection_combinations = updated_truck_selection_combinations
        self.updated_order_selection_mapping_dict = updated_order_selection_mapping_dict
        self.updated_shuffle_together_mapping_dict = updated_shuffle_together_mapping_dict
        self.updated_shuffle_order_schedule_line_mapping_dict = updated_shuffle_order_schedule_line_mapping_dict

    def create_allocation_constraints(self):
        # Constraints
        self.create_only_one_time_selection_constraint()
        self.create_weight_capacity_constraints()
        self.create_volume_capacity_constraints()
        self.create_pallet_capacity_constraints()
        self.create_order_schedule_line_mapping_constraints()
        self.create_shuffle_together_balancing_constraints()
        if stage_two_truck_count_not_within_range:
            self.create_truck_utilization_range_trigger_constraints()
        if stage_two_truck_unused_cost or stage_two_truck_count_not_within_range:
            self.create_min_truck_under_utilization_constraints()
        if order_split_flag:
            self.create_order_split_count_constraints()

        # Objectives
        if stage_two_truck_unused_cost:
            self.create_total_unused_cost_objective()
        if stage_two_truck_count_not_within_range:
            self.create_total_truck_utilization_range_count_cost_objective()
        self.create_total_order_in_other_po_cost_objective()
        self.create_total_order_item_selection_cost_objective()
        if order_split_flag:
            self.create_total_order_splits_cost_objective()


    # Constraints
    def create_only_one_time_selection_constraint(self):
        expr = LinExpr()
        for key, po_details in self.updated_order_truck_mapping.items():
            sales_document, sales_document_item, schedule_line, material, po_number = key
            for r_type, po_list in po_details.items():
                name_key = [str(x) for x in (sales_document, sales_document_item, schedule_line, material, po_number, r_type)]
                ct_name = "Order_Only_One_Time_Selection" + "|" + '|'.join(name_key)
                if r_type == 'integer':
                    for (po, period) in po_list:
                        expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
                    rhs = self.input_data_stage_two.updated_apo_truck_load_dict[po_number][sales_document, sales_document_item, schedule_line, material, r_type]['pallet_spot']
                    self.model.addConstr(expr == rhs, ct_name)
                    expr.clear()
                elif r_type == 'decimal':
                    for (po, period) in po_list:
                        expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
                    self.model.addConstr(expr == 1, ct_name)
                    expr.clear()
        logger.info("Created Order Only One Time Selection Constraints")

    def create_weight_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.updated_truck_selection_combinations.items():
            unused_weight_percent_var = self.model_vars.unused_weight_percent_var[(po, period)]
            weight_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['weight_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                weight = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['weight_per_pallet'], 6)
                expr.add(self.model_vars.order_allocation_var[key], weight)

            name_key = [str(x) for x in (po, period)]
            ct_name = "Weight_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(unused_weight_percent_var == ((weight_limit - expr)/weight_limit)*100, ct_name)
            expr.clear()
        logger.info("Created Weight Capacity Constraints")

    def create_volume_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.updated_truck_selection_combinations.items():
            unused_volume_percent_var = self.model_vars.unused_volume_percent_var[(po, period)]
            volume_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['volume_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                volume = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['volume_per_pallet'], 6)
                expr.add(self.model_vars.order_allocation_var[key], volume)

            name_key = [str(x) for x in (po, period)]
            ct_name = "Volume_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(unused_volume_percent_var == ((volume_limit - expr)/volume_limit)*100, ct_name)
            expr.clear()
        logger.info("Created Volume Capacity Constraints")

    def create_pallet_capacity_constraints(self):
        expr = LinExpr()
        for (po, period), order_list in self.updated_truck_selection_combinations.items():
            unused_pallet_percent_var = self.model_vars.unused_pallet_percent_var[(po, period)]
            pallet_limit = self.input_data_stage_two.input_data.truck_po_level_details[po]['pallet_constraint'] if po in self.input_data_stage_two.input_data.truck_po_level_details else 0
            for key in order_list:
                sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
                if r_type == 'integer':
                    expr.add(self.model_vars.order_allocation_var[key])
                elif r_type == 'decimal':
                    pallet = round(self.input_data_stage_two.updated_order_allocation_combinations[key]['pallet_spot'], 6)
                    expr.add(self.model_vars.order_allocation_var[key], pallet)

            name_key = [str(x) for x in (po, period)]
            ct_name = "Pallet_Capacity_" + "|" + '|'.join(name_key)
            self.model.addConstr(unused_pallet_percent_var ==  ((pallet_limit - expr)/pallet_limit)*100, ct_name)
            expr.clear()
        logger.info("Created Pallet Capacity Constraints")

    def create_min_truck_under_utilization_constraints(self):

        for key, values in self.updated_truck_selection_combinations.items():
            po, period = key
            truck_under_utilization = self.model_vars.truck_under_utilization_var[key]
            unused_weight_percent = self.model_vars.unused_weight_percent_var[key]
            unused_volume_percent = self.model_vars.unused_volume_percent_var[key]
            unused_pallet_percent = self.model_vars.unused_pallet_percent_var[key]
            name_key = [str(x) for x in key]
            ct_name = "ct_min_under_utilization" + "|" + '|'.join(name_key)
            self.model.addConstr(truck_under_utilization == min_(unused_weight_percent, unused_volume_percent,unused_pallet_percent),name=ct_name)
        logger.info("Created Min Truck Under Utilization Constraints")

    def create_truck_utilization_range_trigger_constraints(self):
        # If x > y, then b = 1, otherwise b = 0
        for (po, period) in self.updated_truck_selection_combinations.keys():
            truck_under_utilization = self.model_vars.truck_under_utilization_var[(po, period)]
            truck_under_utilization_range_trigger = self.model_vars.truck_under_utilization_range_trigger_var[(po, period)]
            # Add indicator constraints
            name_key = [str(x) for x in (po, period)]
            ct_name = "Truck_Utilization_Range_Indicator_1" + "|" + '|'.join(name_key)
            self.model.addConstr((truck_under_utilization_range_trigger == 1) >> (truck_under_utilization >= 5), name=ct_name)
            ct_name = "Truck_Utilization_Range_Indicator_2" + "|" + '|'.join(name_key)
            self.model.addConstr((truck_under_utilization_range_trigger == 0) >> (truck_under_utilization <= 5), name=ct_name)
        logger.info("Created Truck Utilization Range Trigger Constraints")

    def create_order_split_count_constraints(self):
        expr = LinExpr()
        for key, po_details in self.model_vars.order_split_count_dict.items():
            sales_document, sales_document_item, schedule_line, material, po_number, po = key
            mul = self.input_data_stage_two.input_data.apo_truck_load_dict[po_number][(sales_document, sales_document_item, schedule_line, material)]['pallet_spot'] + 10
            order_split_count = self.model_vars.order_split_count_var[key]
            for r_type, period_list in po_details.items():
                for period in period_list:
                    expr.add(self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)], 1)
            ct_name = "ct_Order_Split_Count_" + "|" + '|'.join(key)
            self.model.addConstr(expr <= order_split_count * mul,name=ct_name)
            expr.clear()
        logger.info("Created Order Split Count Constraints")

    def create_order_schedule_line_mapping_constraints(self):

        expr_selection = LinExpr()
        expr_mapping = LinExpr()
        for key, po_details in self.updated_order_selection_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            for (po, period), schedule_line_lst in po_details.items():
                order_item_sel_var = self.model_vars.order_item_selection_var[(sales_document, sales_document_item, material, po_number, po, period)]
                expr_selection.add(order_item_sel_var, 1)
                coef = 0
                for (schedule_line, r_typ) in schedule_line_lst:
                    order_allocation_var = self.model_vars.order_allocation_var[(sales_document, sales_document_item, schedule_line, material, po_number, r_typ, po, period)]
                    if r_typ == 'integer':
                        coef += self.input_data_stage_two.updated_order_allocation_combinations[(sales_document, sales_document_item, schedule_line, material, po_number, r_typ, po, period)]['pallet_spot']
                    else:
                        coef += 1
                    expr_mapping.add(order_allocation_var, 1)

                name_key = [str(x) for x in (sales_document, sales_document_item, material, po_number, po, period)]
                ct_name = "Order_Selection_Mapping" + "|" + '|'.join(name_key)
                self.model.addConstr(expr_mapping <= order_item_sel_var * coef, name=ct_name)
                expr_mapping.clear()

            name_key = [str(x) for x in key]
            ct_name = "Order_Selection" + "|" + '|'.join(name_key)
            self.model.addConstr(expr_selection <= self.input_data_stage_two.input_data.model_parameters['max_trucks_per_order_item'] + self.model_vars.order_item_selection_slack_var[key], name=ct_name)
            expr_selection.clear()
        logger.info("Created Order Selection Mapping Constraints")

    def create_shuffle_together_balancing_constraints(self):

        for key, schedule_line_lst in self.updated_shuffle_order_schedule_line_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            # Choose one "anchor" order in each group
            anchor_schedule_line = list(schedule_line_lst)[0]
            # Enforce all others in the group take same truck as anchor
            for (po, period) in self.updated_shuffle_together_mapping_dict[key]:
                if schedule_line_lst == self.updated_shuffle_together_mapping_dict[key][(po, period)]:
                    for (sch_lne, r_typ) in list(schedule_line_lst)[1:]:
                        anchor_order_key = (sales_document, sales_document_item, anchor_schedule_line[0], material, po_number, r_typ, po, period)
                        mapping_order_key = (sales_document, sales_document_item, sch_lne, material, po_number, r_typ, po, period)
                        name_key = [str(x) for x in mapping_order_key]
                        ct_name = "Order_Shuffle_Together" + "|" + '|'.join(name_key)
                        self.model.addConstr(self.model_vars.order_allocation_var[mapping_order_key] ==
                                             self.model_vars.order_allocation_var[anchor_order_key], name=ct_name)
                else:
                    for (sch_lne, r_typ) in self.updated_shuffle_together_mapping_dict[key][(po, period)]:
                        self.model_vars.order_allocation_var[(sales_document, sales_document_item, sch_lne, material, po_number, r_typ, po, period)].ub = 0

        logger.info("Created Shuffle Together Mapping Constraints")

    # Objectives
    def create_total_unused_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.truck_under_utilization_var.keys():
            po, period = key
            expr.add(self.model_vars.truck_under_utilization_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_UNUSED_COST'], -1)
        ct_name = "ct_total_unused_cost"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total UnUsed Cost Constraints")

    def create_total_truck_utilization_range_count_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.truck_under_utilization_range_trigger_var.keys():
            po, period = key
            expr.add(self.model_vars.truck_under_utilization_range_trigger_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_TRUCK_COUNT_NOT_WITH_IN_RANGE'], -1)
        ct_name = "ct_total_truck_count_with_in_range"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Utilization Range Count Constraints")

    def create_total_order_in_other_po_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_allocation_var.keys():
            sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
            if po_number != po:
                expr.add(self.model_vars.order_allocation_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_IN_OTHER_PO_COST'], -1)
        ct_name = "ct_total_order_in_other_po_cost"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order In Other PO Cost Constraints")

    def create_total_order_splits_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_split_count_var.keys():
            sales_document, sales_document_item, schedule_line, material, po_number, po = key
            if po_number != po:
                expr.add(self.model_vars.order_split_count_var[key], 1)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_SPLIT_COST'], -1)
        ct_name = "ct_total_order_split_cost"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order Split Cost Constraints")

    def create_total_order_item_selection_cost_objective(self):
        expr = LinExpr()
        for key in self.model_vars.order_item_selection_slack_var.keys():
            sales_document, sales_document_item, material, po_number = key
            cost = 1
            expr.add(self.model_vars.order_item_selection_slack_var[key], cost)
        expr.add(self.model_vars.global_var['TOTAL_ORDER_ITEM_SELECTION_SLACK'], -1)
        ct_name = "ct_total_order_item_selection_slack"
        self.model.addConstr(expr == 0, name=ct_name)
        expr.clear()
        logger.info("Created Total Order Item Selection Constraints")






