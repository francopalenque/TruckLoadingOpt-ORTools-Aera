import os

SERVICE = "Hershey_TruckLoading_Optimization"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# RUN_MODE controls whether AERA SDK and Gurobi are used.
# Set to "LOCAL" via environment variable to run offline with CSV files.
# Default "AERA" keeps production behaviour unchanged.
RUN_MODE = os.environ.get("RUN_MODE", "AERA")  # "LOCAL" | "AERA"

# Path to static input CSVs used in LOCAL mode.
LOCAL_INPUT_PATH = os.path.join(os.path.dirname(BASE_DIR), "input_data")
# Output directory for LOCAL mode working files (stage CSVs, truck_df, kpi, etc.).
LOCAL_OUTPUT_PATH = os.path.join(BASE_DIR, "local_output")
# Final output directory for LOCAL mode — sibling of input_data/, uses AERA dataset names.
LOCAL_FINAL_OUTPUT_PATH = os.path.join(os.path.dirname(BASE_DIR), "output_data")
bucket = 'P1D'
date_format = '%Y-%m-%d'
ISO_FORMAT_SEPARATOR = "T"
lp_file = False
file_format = 'csv'
activate_stage_two = True

required_bulk_upload_file = ["Hershey_TruckLoading_Input.xlsx"]
required_normal_upload_files = ['apo_truck_load','truck_capacity_details','dc_slot_schedule','general_configurations']


data_column_mapping = {
  "apo_truck_load": {
      "DC": {
      "name": "DC",
      "type": "string"
    },
      "DC Name": {
      "name": "DC Name",
      "type": "string"
    },
      "PO Number": {
          "name": "PO Number",
          "type": "string"
      },
      "Sales Document": {
          "name": "Sales Document",
          "type": "string"
      },
      "Sales Document Item": {
          "name": "Sales Document Item",
          "type": "string"
      },
      "Schedule Line": {
          "name": "Schedule Line",
          "type": "string"
      },
      "Material": {
          "name": "Material",
          "type": "string"
      },
      "Order quantity in Base Unit": {
          "name": "Order quantity in Base Unit",
          "type": "int"
      },
      "Requested Delivery Date": {
          "name": "Requested Delivery Date",
          "type": "date"
      },
      "ATP Availability Date": {
          "name": "ATP Availability Date",
          "type": "date"
      },
      "Order Quantity Unit": {
          "name": "Order Quantity Unit",
          "type": "int"
      },
      "Weight": {
          "name": "Weight",
          "type": "float"
      },
      "Volume": {
          "name": "Volume",
          "type": "float"
      },
      "Confirmed Quantity in Base Unit": {
          "name": "Confirmed Quantity in Base Unit",
          "type": "int"
      },
      "Pallet Spot": {
          "name": "Pallet Spot",
          "type": "float"
      },
      "Priority Line Flag": {
          "name": "CONFIRMED ORDER QUANTITY",
          "type": "string"
      },
      "Pallet Conversion Factor": {
          "name": "Pallet Conversion Factor",
          "type": "int"
      },
      "Weight Conversion Factor": {
          "name": "Weight Conversion Factor",
          "type": "float"
      },
      "Volume Conversion Factor": {
          "name": "Volume Conversion Factor",
          "type": "float"
      },
      "Pallet Spot Conversion Factor": {
          "name": "Pallet Spot Conversion Factor",
          "type": "float"
      },
      "MaterialByCustomer": {
          "name": "MaterialByCustomer",
          "type": "string"
      },
      "Base Unit": {
          "name": "Base Unit",
          "type": "string"
      },
      "Order Creation Date": {
          "name": "Order Creation Date",
          "type": "date"
      },
      "Planned Goods Issue Date": {
          "name": "Planned Goods Issue Date",
          "type": "date"
      },
      "Gross Weight": {
          "name": "Gross Weight",
          "type": "float"
      },
      "Actual Delivery Date": {
          "name": "Actual Delivery Date",
          "type": "date"
      },
      "Delivery Date": {
          "name": "Delivery Date",
          "type": "date"
      },
  },
  "truck_capacity_details": {
      "PO Number": {
          "name": "PO Number",
          "type": "string"
      },
      "DC": {
          "name": "DC",
          "type": "string"
      },
      "Requested Delivery Date": {
          "name": "Requested Delivery Date",
          "type": "date"
      },
      "Total Qty": {
          "name": "Total Qty",
          "type": "int"
      },
      "Total Pallet Size Occupied": {
          "name": "Total Pallet Size Occupied",
          "type": "float"
      },
      "Total Weight Size Occupied": {
          "name": "Total Weight Size Occupied",
          "type": "float"
      },
      "Total Volume Size Occupied": {
          "name": "Total Volume Size Occupied",
          "type": "float"
      },
      "Trailer Size": {
          "name": "Trailer Size",
          "type": "string"
      },
      "Pallet Constraint": {
          "name": "Pallet Constraint",
          "type": "float"
      },
      "Weight Constraint": {
          "name": "Weight Constraint",
          "type": "float"
      },
      "Volume Constraint": {
          "name": "Volume Constraint",
          "type": "float"
      },
      "Pallet Threshold Qty": {
          "name": "Pallet Threshold Qty",
          "type": "float"
      },
      "Weight Threshold Qty": {
          "name": "Weight Threshold Qty",
          "type": "float"
      },
      "Volume Threshold Qty": {
          "name": "Volume Threshold Qty",
          "type": "float"
      },
      "PO Utilization Weight": {
          "name": "PO Utilization Weight",
          "type": "float"
      },
      "PO Utilization Pallet": {
          "name": "PO Utilization Pallet",
          "type": "float"
      },
      "PO Utilization Volume": {
          "name": "PO Utilization Volume",
          "type": "float"
      },
      "Rank": {
          "name": "Rank",
          "type": "int"
      },
  },
  "dc_slot_schedule": {
    "DC": {
      "name": "DC",
      "type": "string"
    },
    "Week Name": {
      "name": "Week Name",
      "type": "string"
    },
    "Number of Slots": {
          "name": "Number of Slots",
          "type": "int"
      },
  },
  "general_configurations": {
      "End Date": {"name": "End Date","type": "date"},
      "Start Date": {"name": "Start Date","type": "date"},
    },
}

# output_files = {'kpi_solution_df.csv':'kpi_solution_df_cons.csv','finial_order_df.csv':'finial_order_df_cons.csv','truck_df.csv':'truck_df_cons.csv','sel_non_sel_df.csv':'sel_non_sel_df_cons.csv','order_po_counts.csv':'order_po_counts_cons.csv'}
finial_output_stage_one = {'kpi_solution_df': [],'finial_order_df': [],'truck_df': [],'sel_non_sel_df':[]}
finial_output_stage_two = {'kpi_solution_df': [],'finial_order_df': [],'truck_df': [],'sel_non_sel_df':[],'order_po_counts':[]}
finial_output = {'kpi_solution_df': [],'finial_order_df': [],'truck_df': [],'sel_non_sel_df':[]}

output_files_col = {'kpi_solution_df': ["scenario_id", "kpi", "value"],
                    'finial_order_df': ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number', 'dc', 'dc_name', 'pallet_spot', 'gross_weight',
                                        'confirmed_quantity_in_base_unit', 'volume', 'requested_delivery_date','atp_availability_date', 'delivery_date', 'original_delivery_date',
                                        'actual_delivery_date', 'requested_delivery_period', 'delivery_period','requested_delivery_day_name', 'delivery_day_name', 'proposed_po',
                                        'proposed_period', 'proposed_requested_delivery_date','order_allocation', 'flag', 'r_type', 'priority_line_flag',
                                        'units_per_pallet', 'weight_per_unit', 'volume_per_unit', 'delivery_date_check_flag', 'weight_check_flag', 'volume_check_flag',
                                        'pallet_check_flag', 'base_unit', 'order_creation_date', 'order_quantity_unit', 'planned_goods_issue_date',
                                        'order_quantity_in_base_unit', 'pallet_spot_conversion_factor', 'materialbycustomer', 'shuffle_together_flag', 'scenario_name'],
                    'truck_df': ['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                        'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                        'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                        'unused_volume_percent','unused_pallet_percent','flag'],
                    'sel_non_sel_df':['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period','original_date', 'truck_selection', 'weight_limit', 'volume_limit',
             'pallet_limit', 'original_weight_used', 'weight_used','original_volume_used', 'volume_used', 'original_pallet_used',
             'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet','unused_weight_percent', 'unused_volume_percent',
             'unused_pallet_percent','flag','action','scenario_name']}

optimization_status = {2: 'OPTIMAL', 9: 'TIME_LIMIT_REACHED', 11: 'INTERRUPTED_BY_USER'}

date_transformation = {'apo_truck_load': ['requested_delivery_date','atp_availability_date','order_creation_date','planned_goods_issue_date','delivery_date','actual_delivery_date'],'truck_capacity_details':['requested_delivery_date']}

# Stage 1
# Mainly Truck Selection, we also have flexibility to maintain original plan (We saw some run time issue in some cases with "TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST" objective.
objective_type = 'Hierarchical'  # Blended, Hierarchical # In Hierarchical: Higher Priority will be solved first
manual_hierarchical = True
objective_sense = 'Minimization'
order_in_original_truck_slack = False
order_in_original_truck_constraint = False
order_slack_flag = True

objectives = {'TOTAL_TRUCK_COUNT': {'weight': 500, 'priority': 50},
              'TOTAL_TRUCK_SELECTION_PREFERENCE': {'weight': 50, 'priority': 50},
              'TOTAL_TRUCK_DELAY_ADVANCE_COST': {'weight': 1, 'priority': 30},
              'TOTAL_ORDER_ITEM_SELECTION_SLACK': {'weight': 1, 'priority': 20},}

# if order_in_original_truck_slack:
#     objectives['TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST'] = {'weight': 1, 'priority': 10}

if order_slack_flag:
    objectives['TOTAL_ORDER_SLACK'] = {'weight': 1, 'priority': 60}

# Reshuffling Schedule Lines to Match Close to the Original Allocation Plan
stage_one_reshuffling = True
stage_one_reshuffling_objective_type = 'Blended'  # Blended, Hierarchical # In Hierarchical: Higher Priority will be solved first
stage_one_reshuffling_manual_hierarchical = False
stage_one_reshuffling_objective_sense = 'Minimization'
stage_one_truck_count_not_within_range = False
stage_one_truck_unused_cost = False

stage_one_reshuffling_objectives = {'TOTAL_ORDER_IN_OTHER_PO_COST': {'weight': 1, 'priority': 30},
                                    'TOTAL_ORDER_ITEM_SELECTION_SLACK': {'weight': 1, 'priority': 20}}

if stage_one_truck_count_not_within_range:
    stage_one_reshuffling_objectives['TOTAL_TRUCK_COUNT_NOT_WITH_IN_RANGE'] = {'weight': 1, 'priority': 50}

if stage_one_truck_unused_cost:
    stage_one_reshuffling_objectives['TOTAL_UNUSED_COST'] = {'weight': 1, 'priority': 40}

# Stage 2
objective_type_stage_two = 'Hierarchical'  # Blended, Hierarchical # In Hierarchical: Higher Priority will be solved first
manual_hierarchical_stage_two = True
objective_sense_stage_two = 'Minimization'
order_in_original_truck_slack_stage_two = False
order_in_original_truck_constraint_stage_two = False
order_split_flag = True
order_slack_flag_stage_two = True

objectives_stage_two = {'TOTAL_TRUCK_COUNT': {'weight': 500, 'priority': 60},
                        'TOTAL_TRUCK_SELECTION_PREFERENCE': {'weight': 50, 'priority': 60},
                        'TOTAL_TRUCK_DELAY_ADVANCE_COST': {'weight': 1, 'priority': 40},
                        'TOTAL_ORDER_ITEM_SELECTION_SLACK': {'weight': 1, 'priority': 30}}

# if order_in_original_truck_slack_stage_two:
#     objectives_stage_two['TOTAL_ORDER_NOT_IN_ORIGINAL_TRUCK_COST'] = {'weight': 1, 'priority': 20}

if order_split_flag:
    objectives_stage_two['TOTAL_ORDER_SPLIT_COST'] = {'weight': 1, 'priority': 10}

if order_slack_flag_stage_two:
    objectives_stage_two['TOTAL_ORDER_SLACK'] = {'weight': 1, 'priority': 70}

# Reshuffling Schedule Lines to Match Close to the Original Allocation Plan
stage_two_reshuffling = True
stage_two_reshuffling_objective_type = 'Blended'  # Blended, Hierarchical # In Hierarchical: Higher Priority will be solved first
stage_two_reshuffling_manual_hierarchical = False
stage_two_reshuffling_objective_sense = 'Minimization'
stage_two_truck_count_not_within_range = False
stage_two_truck_unused_cost = False

stage_two_reshuffling_objectives = {'TOTAL_ORDER_IN_OTHER_PO_COST': {'weight': 1, 'priority': 30},
                                    'TOTAL_ORDER_ITEM_SELECTION_SLACK': {'weight': 1, 'priority': 20}}

if stage_two_truck_count_not_within_range:
    stage_two_reshuffling_objectives['TOTAL_TRUCK_COUNT_NOT_WITH_IN_RANGE'] = {'weight': 1, 'priority': 50}

if stage_two_truck_unused_cost:
    stage_two_reshuffling_objectives['TOTAL_UNUSED_COST'] = {'weight': 1, 'priority': 40}

if order_split_flag:
    stage_two_reshuffling_objectives['TOTAL_ORDER_SPLIT_COST'] = {'weight': 1, 'priority': 10}