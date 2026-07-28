from src.common.logger_config import logger
import pandas as pd
from src.common.utils import find_valid_period


class DataHandlingStageTwo:
    def __init__(self, input_data):
        self.input_data = input_data

        self.updated_apo_truck_load_dict, self.updated_apo_truck_load_df = None, None
        (self.updated_order_allocation_combinations, self.updated_truck_selection_combinations, self.updated_order_truck_mapping,
         self.updated_period_truck_mapping, self.updated_truck_period_mapping, self.updated_original_truck_order_mapping, self.updated_order_selection_mapping_dict,
         self.updated_shuffle_together_mapping_dict, self.updated_shuffle_order_schedule_line_mapping_dict, self.updated_order_with_no_slots) = None, None, None, None, None, None, None, None, None, None


    def prepare_model_data(self):
        self.updated_apo_truck_load_dict, self.updated_apo_truck_load_df = self.modify_apo_truck_load()
        (self.updated_order_allocation_combinations, self.updated_truck_selection_combinations, self.updated_order_truck_mapping,
         self.updated_period_truck_mapping, self.updated_truck_period_mapping, self.updated_original_truck_order_mapping, self.updated_order_selection_mapping_dict,
         self.updated_shuffle_together_mapping_dict, self.updated_shuffle_order_schedule_line_mapping_dict, self.updated_order_with_no_slots) = self.create_modified_apo_truck_load_combinations()


    def modify_apo_truck_load(self):
        apo_truck_load_df = self.input_data.apo_truck_load_df

        row_lst = []
        for idx, row in apo_truck_load_df.iterrows():
            int_pallet_quantity = int(row['pallet_spot'])
            decimal_pallet_quantity = row['pallet_spot'] - int_pallet_quantity
            # Create a row for the integer part
            if int_pallet_quantity > 0:
                integer_row = row.copy()
                integer_row['pallet_spot'] = int_pallet_quantity
                integer_row['row_type'] = 'integer'
                integer_row['confirmed_quantity_in_base_unit'] = int_pallet_quantity * integer_row['units_per_pallet']
                integer_row['weight_per_pallet'] = integer_row['units_per_pallet'] * integer_row['weight_per_unit']
                integer_row['volume_per_pallet'] = integer_row['units_per_pallet'] * integer_row['volume_per_unit']
                integer_row['shuffle_together_flag'] = 'N'
                row_lst.append(integer_row)
            # Create a row for the decimal part (only if > 0)
            if decimal_pallet_quantity > 0:
                decimal_row = row.copy()
                decimal_row['pallet_spot'] = decimal_pallet_quantity
                decimal_row['row_type'] = 'decimal'
                decimal_row['confirmed_quantity_in_base_unit'] = decimal_row['confirmed_quantity_in_base_unit'] - int_pallet_quantity * decimal_row['units_per_pallet']
                decimal_row['weight_per_pallet'] = decimal_row['confirmed_quantity_in_base_unit'] * decimal_row['weight_per_unit']
                decimal_row['volume_per_pallet'] = decimal_row['confirmed_quantity_in_base_unit'] * decimal_row['volume_per_unit']
                row_lst.append(decimal_row)

        # Convert to new DataFrame
        updated_apo_truck_load_df = pd.DataFrame(row_lst)

        value_columns = ['dc','dc_name','requested_delivery_date','atp_availability_date','delivery_date','original_delivery_date','actual_delivery_date','pallet_spot','gross_weight','confirmed_quantity_in_base_unit',
                         'volume','requested_delivery_period','delivery_period','requested_delivery_day_name','delivery_day_name',
                         'weight_per_pallet','volume_per_pallet','priority_line_flag','units_per_pallet','weight_per_unit','volume_per_unit',
                         'base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date',
                         'order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','shuffle_together_flag']

        updated_apo_truck_load_dict = {}
        for index, row in updated_apo_truck_load_df.iterrows():
            if row['po_number'] not in updated_apo_truck_load_dict:
                updated_apo_truck_load_dict[row['po_number']] = {}
            if (row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material'], row['row_type']) not in updated_apo_truck_load_dict[row['po_number']]:
                updated_apo_truck_load_dict[row['po_number']][(row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material'], row['row_type'])] = {}
            updated_apo_truck_load_dict[row['po_number']][(row['sales_document'], row['sales_document_item'], row['schedule_line'], row['material'], row['row_type'])] = dict((k, row[k]) for k in value_columns)
        return updated_apo_truck_load_dict, updated_apo_truck_load_df


    def create_modified_apo_truck_load_combinations(self):
        updated_order_allocation_combinations = {}
        updated_order_with_no_slots = {}
        for po_number, po_values in self.updated_apo_truck_load_dict.items():
            for key, values in po_values.items():
                sales_document, sales_document_item, schedule_line, material, r_type = key
                if values['priority_line_flag'] == 'Y':
                    if values['requested_delivery_period'] <= values['delivery_period']:
                        period_lst = []
                        result = find_valid_period(values['delivery_period'], self.input_data.horizon,self.input_data.period_day_name_mapping, self.input_data.dc_slot_schedule_dict)
                        if result is not None:
                            period_lst.append(result)
                    else:
                        period_lst = []
                        # Try within requested window
                        for period in range(values['delivery_period'], values['requested_delivery_period'] + 1):
                            day_name = self.input_data.period_day_name_mapping[period]['day_name']
                            if self.input_data.dc_slot_schedule_dict.get(day_name, 0) > 0:
                                period_lst.append(period)

                        # If nothing found, fallback after requested
                        if not period_lst:
                            result = find_valid_period(values['requested_delivery_period'], self.input_data.horizon, self.input_data.period_day_name_mapping, self.input_data.dc_slot_schedule_dict)
                            if result is not None:
                                period_lst.append(result)
                else:
                    period_lst = list(range(1,self.input_data.horizon+1))
                has_valid_slot = False
                for po in self.input_data.truck_po_level_details.keys():
                    for period in period_lst:
                        if period >= values['delivery_period']:
                            if self.input_data.period_day_name_mapping[period]['day_name'] in self.input_data.dc_slot_schedule_dict:
                                if self.input_data.dc_slot_schedule_dict[self.input_data.period_day_name_mapping[period]['day_name']] > 0:
                                    updated_order_allocation_combinations[(sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period)] = values
                                    has_valid_slot = True
                if not has_valid_slot:
                    updated_order_with_no_slots[(sales_document, sales_document_item, schedule_line, material, po_number)] = values
        logger.info("Order Allocation Combinations Created with {} combinations".format(len(updated_order_allocation_combinations)))

        updated_truck_selection_combinations = {}
        updated_order_truck_mapping = {}
        updated_period_truck_mapping = {}
        updated_truck_period_mapping = {}
        updated_original_truck_order_mapping = {}
        updated_order_selection_mapping_dict = {}
        updated_shuffle_together_mapping_dict = {}
        updated_shuffle_order_schedule_line_mapping_dict = {}
        for key, values in updated_order_allocation_combinations.items():
            sales_document, sales_document_item, schedule_line, material, po_number, r_type, po, period = key
            if (po, period) not in updated_truck_selection_combinations:
                updated_truck_selection_combinations[(po, period)] = []
            updated_truck_selection_combinations[(po, period)].append(key)

            if period not in updated_period_truck_mapping:
                updated_period_truck_mapping[period] = set()
            updated_period_truck_mapping[period].add(po)

            if po not in updated_truck_period_mapping:
                updated_truck_period_mapping[po] = set()
            updated_truck_period_mapping[po].add(period)

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


            if (po, period) not in updated_original_truck_order_mapping:
                updated_original_truck_order_mapping[(po, period)] = set()
            if po_number == po:
                updated_original_truck_order_mapping[(po, period)].add(key)

        return (updated_order_allocation_combinations, updated_truck_selection_combinations, updated_order_truck_mapping, updated_period_truck_mapping, updated_truck_period_mapping,
                updated_original_truck_order_mapping, updated_order_selection_mapping_dict, updated_shuffle_together_mapping_dict, updated_shuffle_order_schedule_line_mapping_dict, updated_order_with_no_slots)





































