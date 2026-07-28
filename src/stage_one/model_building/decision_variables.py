from gurobipy import GRB
from src.common.logger_config import logger
from src.common.constants import order_in_original_truck_slack, order_slack_flag, stage_one_truck_count_not_within_range, stage_one_truck_unused_cost


class DecisionVariable:
    def __init__(self, model, input_data):
        self.model = model
        self.input_data = input_data

        self.order_allocation_var = dict()
        self.global_var = dict()
        self.truck_selection_var = dict()
        self.order_in_original_truck_slack_var = dict()
        self.order_non_selection_var = dict()
        self.order_item_selection_var, self.order_item_selection_slack_var = dict(), dict()

    def create_decision_variables(self):
        self.order_allocation_var = self.create_order_allocation_variables()
        self.global_var = self.create_global_variables()
        self.truck_selection_var = self.create_truck_variables()
        self.order_item_selection_var, self.order_item_selection_slack_var = self.create_order_selection_variables()
        if order_slack_flag:
            self.order_non_selection_var = self.create_order_selection_slack()
        if order_in_original_truck_slack:
            self.order_in_original_truck_slack_var = self.create_order_in_original_truck_slack_variables()


    def create_order_allocation_variables(self):
        order_allocation_var = dict()
        for key, values in self.input_data.order_allocation_combinations.items():
            sales_document, sales_document_item, schedule_line, material, po_number, po, period = key
            name_key = [str(x) for x in key]
            var_name = "Order_Allocation_Var" + "|" + '|'.join(name_key)
            order_allocation_var[key] = self.model.addVar(lb=0,ub=1,name=var_name, vtype=GRB.BINARY)
        logger.info("Order Allocation Variables Created")
        return order_allocation_var

    def create_truck_variables(self):
        truck_selection_var = dict()
        for key, values in self.input_data.truck_selection_combinations.items():
            po, period = key
            name_key = [str(x) for x in key]
            var_name = "Truck_Selection_Var" + "|" + '|'.join(name_key)
            truck_selection_var[key] = self.model.addVar(lb=0,ub=1,name=var_name, vtype=GRB.BINARY)
        logger.info("Truck Variables Created")
        return truck_selection_var

    def create_order_in_original_truck_slack_variables(self):
        order_in_original_truck_slack_var = dict()
        for (po, period), order_list in self.input_data.original_truck_order_mapping.items():
            name_key = [str(x) for x in (po, period)]
            var_name = "Order_In_Original_Truck_Slack_Var" + "|" + '|'.join(name_key)
            order_in_original_truck_slack_var[(po, period)] = self.model.addVar(lb=0, ub= len(order_list),name=var_name, vtype=GRB.INTEGER)
        logger.info("Order In Original Truck Variables Created")
        return order_in_original_truck_slack_var

    def create_global_variables(self):
        global_var = dict()
        truck_num = len(self.input_data.truck_po_level_details.keys())
        global_var["TOTAL_TRUCK_COUNT"] = self.model.addVar(lb=0,ub=truck_num,name="TOTAL_TRUCK_COUNT")
        global_var["TOTAL_TRUCK_SELECTION_PREFERENCE"] = self.model.addVar(lb=0,ub=truck_num * 101, name="TOTAL_TRUCK_SELECTION_PREFERENCE")
        global_var["TOTAL_TRUCK_DELAY_ADVANCE_COST"] = self.model.addVar(lb=0,ub=truck_num * self.input_data.horizon * 2,name="TOTAL_TRUCK_DELAY_ADVANCE_COST")
        global_var["TOTAL_ORDER_ITEM_SELECTION_SLACK"] = self.model.addVar(lb=0,ub=truck_num * len(self.input_data.order_selection_mapping_dict.keys()),name="TOTAL_ORDER_ITEM_SELECTION_SLACK")
        if order_in_original_truck_slack:
            global_var["TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST"] = self.model.addVar(lb=0,ub=len(self.input_data.order_truck_mapping.keys()) * 2,name="TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST")
        if order_slack_flag:
            global_var["TOTAL_ORDER_SLACK"] = self.model.addVar(lb=0,ub=len(self.input_data.order_truck_mapping.keys()) * 100,name="TOTAL_ORDER_SLACK")
        logger.info("Global Variables Created")
        return global_var

    def create_order_selection_slack(self):
        order_non_selection_var = dict()
        for key, po_list in self.input_data.order_truck_mapping.items():
            name_key = [str(x) for x in key]
            var_name = "Order_Missed_Slack_Var" + "|" + '|'.join(name_key)
            order_non_selection_var[key] = self.model.addVar(lb=0, ub=1, name=var_name, vtype=GRB.BINARY)
        logger.info("Order Selection Slack Variables Created")
        return order_non_selection_var

    def create_order_selection_variables(self):
        order_item_selection_var = dict()
        order_item_selection_slack_var = dict()
        for key, po_details in self.input_data.order_selection_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            for (po, period), values in po_details.items():
                new_key = (sales_document, sales_document_item, material, po_number, po, period)
                name_key = [str(x) for x in new_key]
                var_name = "Order_Selection_Var" + "|" + '|'.join(name_key)
                order_item_selection_var[new_key] = self.model.addVar(lb=0,ub=1,name=var_name, vtype=GRB.BINARY)

            name_key = [str(x) for x in key]
            var_name = "Order_Selection_Slack_Var" + "|" + '|'.join(name_key)
            order_item_selection_slack_var[key] = self.model.addVar(lb=0, ub=len(po_details.keys()),name=var_name, vtype=GRB.INTEGER)
        logger.info("Order Selection Variables Created")
        return order_item_selection_var, order_item_selection_slack_var


class ReshufflingStageOneDecisionVariable:
    def __init__(self, model, updated_order_allocation_combinations, updated_truck_selection_combinations, selected_order_dict, updated_order_selection_mapping_dict,updated_order_truck_mapping):
        self.model = model
        self.updated_order_allocation_combinations = updated_order_allocation_combinations
        self.updated_truck_selection_combinations = updated_truck_selection_combinations
        self.selected_order_dict = selected_order_dict
        self.updated_order_selection_mapping_dict = updated_order_selection_mapping_dict
        self.updated_order_truck_mapping = updated_order_truck_mapping

        self.order_allocation_var = dict()
        self.global_var = dict()
        (self.unused_weight_percent_var, self.unused_volume_percent_var, self.unused_pallet_percent_var, self.truck_under_utilization_var,
         self.truck_under_utilization_range_trigger_var)  = dict(), dict(), dict(), dict(), dict()
        self.order_item_selection_var, self.order_item_selection_slack_var = dict(), dict()

    def create_allocation_decision_variables(self):
        self.order_allocation_var = self.create_order_allocation_variables()
        self.global_var = self.create_global_variables()
        (self.unused_weight_percent_var, self.unused_volume_percent_var, self.unused_pallet_percent_var, self.truck_under_utilization_var,
         self.truck_under_utilization_range_trigger_var) = self.create_truck_variables()
        self.order_item_selection_var, self.order_item_selection_slack_var = self.create_order_selection_variables()


    def create_order_allocation_variables(self):
        order_allocation_var = dict()
        for key in self.updated_order_allocation_combinations:
            sales_document, sales_document_item, schedule_line, material, po_number, po, period = key
            name_key = [str(x) for x in key]
            var_name = "Order_Allocation_Var" + "|" + '|'.join(name_key)
            order_allocation_var[key] = self.model.addVar(lb=0,ub=1,name=var_name, vtype=GRB.BINARY)
        logger.info("Order Allocation Variables Created")
        return order_allocation_var

    def create_truck_variables(self):
        unused_weight_percent_var = dict()
        unused_volume_percent_var = dict()
        unused_pallet_percent_var = dict()
        truck_under_utilization_var = dict()
        truck_under_utilization_range_trigger_var = dict()

        for key, values in self.updated_truck_selection_combinations.items():
            po, period = key
            name_key = [str(x) for x in key]

            var_name = "UnUsed_Weight_Percent_Var" + "|" + '|'.join(name_key)
            unused_weight_percent_var[key] = self.model.addVar(lb=0, ub=100,name=var_name, vtype=GRB.CONTINUOUS)
            var_name = "UnUsed_Volume_Percent_Var" + "|" + '|'.join(name_key)
            unused_volume_percent_var[key] = self.model.addVar(lb=0, ub=100,name=var_name, vtype=GRB.CONTINUOUS)
            var_name = "UnUsed_Pallet_Percent_Var" + "|" + '|'.join(name_key)
            unused_pallet_percent_var[key] = self.model.addVar(lb=0, ub=100,name=var_name, vtype=GRB.CONTINUOUS)
            if stage_one_truck_unused_cost or stage_one_truck_count_not_within_range:
                var_name = "Truck_Under_Utilization_Var" + "|" + '|'.join(name_key)
                truck_under_utilization_var[key] = self.model.addVar(lb=0, ub=100,name=var_name, vtype=GRB.CONTINUOUS)

            if stage_one_truck_count_not_within_range:
                var_name = "Truck_Under_Utilization_Range_Trigger_Var" + "|" + '|'.join(name_key)
                truck_under_utilization_range_trigger_var[key] = self.model.addVar(lb=0, ub=1,name=var_name, vtype=GRB.BINARY)

        logger.info("Truck Variables Created")
        return unused_weight_percent_var, unused_volume_percent_var,unused_pallet_percent_var, truck_under_utilization_var, truck_under_utilization_range_trigger_var

    def create_global_variables(self):
        allocation_global_var = dict()
        truck_num = len(self.updated_truck_selection_combinations.keys())
        if stage_one_truck_unused_cost:
            allocation_global_var["TOTAL_UNUSED_COST"] = self.model.addVar(lb=0,ub=truck_num * 100,name="TOTAL_UNUSED_COST")
        if stage_one_truck_count_not_within_range:
            allocation_global_var["TOTAL_TRUCK_COUNT_NOT_WITH_IN_RANGE"] = self.model.addVar(lb=0,ub=truck_num,name="TOTAL_TRUCK_COUNT_NOT_WITH_IN_RANGE")
        allocation_global_var["TOTAL_ORDER_IN_OTHER_PO_COST"] = self.model.addVar(lb=0,ub=len(self.updated_order_truck_mapping.keys()) * 2,name="TOTAL_ORDER_IN_OTHER_PO_COST")
        allocation_global_var["TOTAL_ORDER_ITEM_SELECTION_SLACK"] = self.model.addVar(lb=0,ub=truck_num * len(self.updated_order_selection_mapping_dict.keys()),name="TOTAL_ORDER_ITEM_SELECTION_SLACK")
        logger.info("Global Variables Created")
        return allocation_global_var

    def create_order_selection_variables(self):
        order_item_selection_var = dict()
        order_item_selection_slack_var = dict()
        for key, po_details in self.updated_order_selection_mapping_dict.items():
            sales_document, sales_document_item, material, po_number = key
            for (po, period), values in po_details.items():
                new_key = (sales_document, sales_document_item, material, po_number, po, period)
                name_key = [str(x) for x in new_key]
                var_name = "Order_Selection_Var" + "|" + '|'.join(name_key)
                order_item_selection_var[new_key] = self.model.addVar(lb=0,ub=1,name=var_name, vtype=GRB.BINARY)

            name_key = [str(x) for x in key]
            var_name = "Order_Selection_Slack_Var" + "|" + '|'.join(name_key)
            order_item_selection_slack_var[key] = self.model.addVar(lb=0, ub=len(po_details.keys()),name=var_name, vtype=GRB.INTEGER)
        logger.info("Order Selection Variables Created")
        return order_item_selection_var, order_item_selection_slack_var




