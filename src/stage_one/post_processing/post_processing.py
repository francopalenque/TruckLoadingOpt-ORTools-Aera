import pandas as pd
from src.common.logger_config import logger
import numpy as np
import traceback


class PostProcessor:
    def __init__(self,input_data,raw_output_dict,output_path, apo_truck_load_fully_utilized, truck_details_fully_utilized, dc, actual_truck_count):
        self.input_data = input_data
        self.raw_output_dict = raw_output_dict
        self.output_path = output_path
        self.apo_truck_load_fully_utilized = apo_truck_load_fully_utilized
        self.truck_details_fully_utilized = truck_details_fully_utilized
        self.dc = dc
        self.actual_truck_count = actual_truck_count
        self.output_dict, self.proposed_po_count = None, None
        self.actual_lines = len(self.input_data.apo_truck_load_df.drop_duplicates(subset=['sales_document', 'sales_document_item','schedule_line','material','po_number','requested_delivery_period']))
        self.assign_lines = None

    def results(self):
        self.output_dict, self.proposed_po_count = self.post_process_results()


    def post_process_results(self):
        output_dict = {}
        logger.info("Creating Solution DataFrames")

        # KPIs DataFrame
        try:
            logger.info("Creating KPIs DataFrame")
            kpi_lst = []
            for key, value in self.raw_output_dict['kpi_dict'].items():
                kpi_lst.append([self.input_data.plan_id, key, value])
            kpi_solution_df = pd.DataFrame(kpi_lst,columns=["scenario_id", "kpi", "value"])
            output_dict['kpi_solution_df'] = kpi_solution_df
            logger.info("KPIs DataFrame Created")
        except Exception as e:
            logger.warning("KPI DataFrame missing or empty " + str(e))
            kpi_solution_df = pd.DataFrame(columns=["scenario_id", "kpi", "value"])
            output_dict['kpi_solution_df'] = kpi_solution_df
            logger.warning("KPIs DataFrame Empty")

        # Order DataFrame
        try:
            logger.info("Creating Order DataFrame")

            column_seq = ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material','po_number', 'dc', 'dc_name',
                           'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume','requested_delivery_date', 'atp_availability_date','delivery_date','original_delivery_date','actual_delivery_date',
                          'requested_delivery_period', 'delivery_period', 'requested_delivery_day_name','delivery_day_name', 'proposed_po', 'proposed_period','shuffle_together_flag',
                          'proposed_requested_delivery_date', 'order_allocation', 'flag', 'priority_line_flag','units_per_pallet', 'weight_per_unit', 'volume_per_unit',
                          'base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date','order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','solver_rejected']

            finial_order_df = pd.DataFrame(columns=column_seq)
            orders_with_no_slots_df = pd.DataFrame(columns=column_seq)
            if len(self.input_data.order_allocation_combinations) > 0:
                # Step 1: Convert to DataFrame
                order_allocation_combination_df = pd.DataFrame.from_dict(self.input_data.order_allocation_combinations, orient='index')
                # Step 2: Set MultiIndex from the tuple keys
                index_key = ['sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number', 'proposed_po', 'proposed_period']
                order_allocation_combination_df.index = pd.MultiIndex.from_tuples(order_allocation_combination_df.index, names=index_key)
                order_allocation_combination_df = order_allocation_combination_df.reset_index()

                order_lst = []
                for key, values in self.input_data.order_allocation_combinations.items():
                    sales_document, sales_document_item, schedule_line, material, po_number, po, period = key
                    date = self.input_data.period_to_date[period]
                    order_allocation = np.round(self.raw_output_dict['order_allocation_dict'][key])

                    order_lst.append([self.input_data.plan_id,sales_document, sales_document_item, schedule_line, material, po_number, po, period,date,order_allocation])

                order_df = pd.DataFrame(order_lst,columns=['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material','po_number', 'proposed_po', 'proposed_period','proposed_requested_delivery_date','order_allocation'])
                finial_order_df = pd.merge(order_allocation_combination_df,order_df,how='left',on=['sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number', 'proposed_po', 'proposed_period'])
                finial_order_df['flag'] = 'SolverResults'
            self.assign_lines = len(finial_order_df[finial_order_df['order_allocation'] == 1])

            if len(self.input_data.order_with_no_slots) > 0:
                # Step 1: Convert to DataFrame
                orders_with_no_slots_df = pd.DataFrame.from_dict(self.input_data.order_with_no_slots,orient='index')
                # Step 2: Set MultiIndex from the tuple keys
                index_key = ['sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number']
                orders_with_no_slots_df.index = pd.MultiIndex.from_tuples(orders_with_no_slots_df.index, names=index_key)
                orders_with_no_slots_df = orders_with_no_slots_df.reset_index()
                orders_with_no_slots_df['scenario_id'] = self.input_data.plan_id
                orders_with_no_slots_df['proposed_po'] = None
                orders_with_no_slots_df['proposed_period'] = None
                orders_with_no_slots_df['proposed_requested_delivery_date'] = None
                orders_with_no_slots_df['order_allocation'] = 0
                orders_with_no_slots_df['flag'] = 'OrderWithNoSlots'
                orders_with_no_slots_df['solver_rejected'] = 0
                orders_with_no_slots_df = orders_with_no_slots_df[column_seq]

            if len(self.apo_truck_load_fully_utilized) > 0:
                self.apo_truck_load_fully_utilized['proposed_po'] = self.apo_truck_load_fully_utilized['po_number']
                self.apo_truck_load_fully_utilized['proposed_requested_delivery_date'] = self.apo_truck_load_fully_utilized['requested_delivery_date']
                self.apo_truck_load_fully_utilized['order_allocation'] = 1
                self.apo_truck_load_fully_utilized['scenario_id'] = self.input_data.plan_id
                self.apo_truck_load_fully_utilized["requested_delivery_period"] = self.apo_truck_load_fully_utilized["requested_delivery_date"].apply(lambda x: self.input_data.date_to_period[x])
                self.apo_truck_load_fully_utilized["delivery_period"] =  self.apo_truck_load_fully_utilized["delivery_date"].apply(lambda x: self.input_data.date_to_period[x])
                self.apo_truck_load_fully_utilized['proposed_period'] = self.apo_truck_load_fully_utilized['requested_delivery_period']
                self.apo_truck_load_fully_utilized['original_delivery_date'] = self.apo_truck_load_fully_utilized['delivery_date']
                self.apo_truck_load_fully_utilized['flag'] = 'ActuallyFullyUtilized'
                self.apo_truck_load_fully_utilized = self.apo_truck_load_fully_utilized.rename(columns={'pallet_conversion_factor': 'units_per_pallet', 'weight_conversion_factor': 'weight_per_unit',
                             'volume_conversion_factor': 'volume_per_unit'})
                self.apo_truck_load_fully_utilized['solver_rejected'] = 0
                self.apo_truck_load_fully_utilized = self.apo_truck_load_fully_utilized[column_seq]

            left_over_apo_truck_load = self.input_data.input_tables_dict['left_over_apo_truck_load']
            print(left_over_apo_truck_load)
            if len(left_over_apo_truck_load) > 0:
                left_over_apo_truck_load['proposed_po'] = self.input_data.garbage_truck_po_number
                left_over_apo_truck_load['order_allocation'] = 1
                left_over_apo_truck_load['scenario_id'] = self.input_data.plan_id
                left_over_apo_truck_load["requested_delivery_period"] = left_over_apo_truck_load["requested_delivery_date"].apply(lambda x: self.input_data.date_to_period[x])
                # left_over_apo_truck_load["delivery_period"] =  left_over_apo_truck_load["delivery_date"].apply(lambda x: self.input_data.date_to_period[x])
                left_over_apo_truck_load["delivery_period"] = None
                left_over_apo_truck_load['proposed_period'] = self.input_data.garbage_truck_period
                left_over_apo_truck_load['proposed_requested_delivery_date'] = self.input_data.period_to_date[self.input_data.garbage_truck_period] if self.input_data.garbage_truck_period is not None else None
                left_over_apo_truck_load['original_delivery_date'] = left_over_apo_truck_load['delivery_date']
                left_over_apo_truck_load['flag'] = 'LeftOverAPOTruckLoad'
                left_over_apo_truck_load = left_over_apo_truck_load.rename(columns={'pallet_conversion_factor': 'units_per_pallet', 'weight_conversion_factor': 'weight_per_unit',
                             'volume_conversion_factor': 'volume_per_unit'})
                left_over_apo_truck_load['solver_rejected'] = 0
                left_over_apo_truck_load = left_over_apo_truck_load[column_seq]
            else:
                left_over_apo_truck_load = pd.DataFrame(columns=column_seq)

            # Build DataFrame from order_non_selection_var (solver rejected lines)
            # Key: (sales_document, sales_document_item, schedule_line, material, po_number)
            # Value: 1 = solver explicitly rejected this order line (extra line, doesn't fit any truck)
            order_non_selection_dict = self.raw_output_dict.get('order_non_selection_dict', {})
            if order_non_selection_dict:
                non_sel_lst = []
                for key, value in order_non_selection_dict.items():
                    sales_document, sales_document_item, schedule_line, material, po_number = key
                    non_sel_lst.append([sales_document, sales_document_item, schedule_line, material, po_number, value])
                non_sel_df = pd.DataFrame(non_sel_lst,columns=['sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number', 'solver_rejected'])
                non_sel_df = non_sel_df[non_sel_df['solver_rejected'] >= 1]
                finial_order_df = pd.merge(finial_order_df, non_sel_df, how='left',on=['sales_document', 'sales_document_item', 'schedule_line', 'material','po_number'],indicator=True)
                # Selected but could be some partially selected
                selected_order_df = finial_order_df[finial_order_df['order_allocation'] >= 1]
                # Completed non selected orders
                non_selected_order_df = finial_order_df[(finial_order_df['order_allocation'] <= 0) & (finial_order_df['solver_rejected'] >= 1)]
                non_selected_order_df = non_selected_order_df.drop(columns=['flag', 'proposed_po', 'proposed_period', 'proposed_requested_delivery_date'])
                non_selected_order_df = non_selected_order_df.drop_duplicates()
                non_selected_order_df['flag'] = 'Solver Rejected Line'
                non_selected_order_df['proposed_po'] = self.input_data.garbage_truck_po_number
                non_selected_order_df['proposed_period'] = self.input_data.garbage_truck_period
                non_selected_order_df['proposed_requested_delivery_date'] = self.input_data.period_to_date[self.input_data.garbage_truck_period] if self.input_data.garbage_truck_period is not None else None
                finial_order_df = pd.concat([selected_order_df, non_selected_order_df], ignore_index=True)
                finial_order_df = finial_order_df[column_seq]
                finial_order_df['solver_rejected'] = finial_order_df['solver_rejected'].fillna(0)
            else:
                finial_order_df = finial_order_df[finial_order_df['order_allocation'] >= 1]
                finial_order_df['solver_rejected'] = 0

            if len(self.apo_truck_load_fully_utilized) > 0:
                con_finial_order_df = pd.concat([finial_order_df,self.apo_truck_load_fully_utilized])
            else:
                con_finial_order_df = finial_order_df

            if len(orders_with_no_slots_df) > 0:
                con_finial_order_df = pd.concat([con_finial_order_df,orders_with_no_slots_df])

            if len(left_over_apo_truck_load) > 0:
                con_finial_order_df = pd.concat([con_finial_order_df,left_over_apo_truck_load])

            # con_finial_order_df['delivery_date_check_flag'] = np.where(con_finial_order_df['proposed_period'] >= con_finial_order_df['delivery_period'], True, False)
            con_finial_order_df['delivery_date_check_flag'] = np.where(    con_finial_order_df['delivery_period'].isna(), True,con_finial_order_df['proposed_period'] >= con_finial_order_df['delivery_period'].fillna(0))
            con_finial_order_df['weight_check_flag'] = con_finial_order_df.apply(lambda row: row['gross_weight'] <= self.input_data.truck_po_level_details.get(row['proposed_po'], {}).get('weight_constraint', 0),axis=1)
            con_finial_order_df['volume_check_flag'] = con_finial_order_df.apply(lambda row: row['volume'] <= self.input_data.truck_po_level_details.get(row['proposed_po'], {}).get('volume_constraint', 0),axis=1)
            con_finial_order_df['pallet_check_flag'] = con_finial_order_df.apply(lambda row: row['pallet_spot'] <= self.input_data.truck_po_level_details.get(row['proposed_po'],{}).get('pallet_constraint', 0), axis=1)
            con_finial_order_df['r_type'] = None
            con_finial_order_df['scenario_name'] = 'stage_one'
            con_finial_order_df = con_finial_order_df[['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line','material', 'po_number', 'dc', 'dc_name',
                   'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume','requested_delivery_date', 'atp_availability_date','delivery_date','original_delivery_date','actual_delivery_date',
                   'requested_delivery_period', 'delivery_period','requested_delivery_day_name', 'delivery_day_name',
                   'proposed_po', 'proposed_period', 'proposed_requested_delivery_date','order_allocation', 'flag','r_type',
                    'priority_line_flag', 'units_per_pallet','weight_per_unit', 'volume_per_unit', 'delivery_date_check_flag',
                   'weight_check_flag', 'volume_check_flag', 'pallet_check_flag','base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date',
                                                       'order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','shuffle_together_flag','scenario_name']]
            output_dict['finial_order_df'] = con_finial_order_df
            logger.info("Order Solution DataFrame Created")

        except Exception as e:
            logger.warning("Order Solution DataFrame missing or empty " + str(e))
            logger.warning(f"Result: {traceback.format_exc()}")
            column_seq = ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material','po_number', 'dc', 'dc_name',
                           'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume','requested_delivery_date', 'atp_availability_date','delivery_date','original_delivery_date','actual_delivery_date',
                          'requested_delivery_period', 'delivery_period', 'requested_delivery_day_name','delivery_day_name', 'proposed_po', 'proposed_period','shuffle_together_flag',
                          'proposed_requested_delivery_date', 'order_allocation', 'flag', 'priority_line_flag','units_per_pallet', 'weight_per_unit', 'volume_per_unit',
                          'base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date','order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','solver_rejected']

            finial_order_df = pd.DataFrame(columns=['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line','material', 'po_number', 'dc', 'dc_name',
                   'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume','requested_delivery_date', 'atp_availability_date','delivery_date','original_delivery_date','actual_delivery_date',
                   'requested_delivery_period', 'delivery_period','requested_delivery_day_name', 'delivery_day_name',
                   'proposed_po', 'proposed_period', 'proposed_requested_delivery_date','order_allocation', 'flag','r_type',
                'priority_line_flag', 'units_per_pallet','weight_per_unit', 'volume_per_unit', 'delivery_date_check_flag',
                   'weight_check_flag', 'volume_check_flag', 'pallet_check_flag','base_unit','order_creation_date','order_quantity_unit','planned_goods_issue_date',
                                                    'order_quantity_in_base_unit','pallet_spot_conversion_factor','materialbycustomer','shuffle_together_flag','scenario_name'])
            left_over_apo_truck_load = pd.DataFrame(columns=column_seq)
            output_dict['finial_order_df'] = finial_order_df
            logger.warning("Order Solution DataFrame Empty")

        # Truck DataFrame
        try:
            logger.info("Creating Truck Details DataFrame")
            truck_lst = []
            for key, values in self.input_data.truck_selection_combinations.items():
                po, period = key
                date = self.input_data.period_to_date[period]
                truck_selection = np.round(self.raw_output_dict['truck_selection_dict'][key])
                weight_limit = self.input_data.truck_po_level_details[po]['weight_constraint'] if po in self.input_data.truck_po_level_details else 0
                volume_limit = self.input_data.truck_po_level_details[po]['volume_constraint'] if po in self.input_data.truck_po_level_details else 0
                pallet_limit = self.input_data.truck_po_level_details[po]['pallet_constraint'] if po in self.input_data.truck_po_level_details else 0
                original_period , original_date, original_weight_used, original_volume_used, original_pallet_used = None,None,None,None,None
                if po in self.input_data.truck_po_level_details:
                    original_period = self.input_data.truck_po_level_details[po]['requested_delivery_period']
                    original_date = self.input_data.truck_po_level_details[po]['requested_delivery_date']
                    original_weight_used = self.input_data.truck_po_level_details[po]['total_weight_size_occupied']
                    original_volume_used = self.input_data.truck_po_level_details[po]['total_volume_size_occupied']
                    original_pallet_used = self.input_data.truck_po_level_details[po]['total_pallet_size_occupied']

                weight_used = 0
                for so in values:
                    weight = self.input_data.order_allocation_combinations[so]['gross_weight']
                    weight_used += np.round(self.raw_output_dict['order_allocation_dict'][so])  * weight
                unused_weight_percent = (weight_limit * truck_selection - weight_used) / weight_limit
                volume_used = 0
                for so in values:
                    volume = self.input_data.order_allocation_combinations[so]['volume']
                    volume_used += np.round(self.raw_output_dict['order_allocation_dict'][so]) * volume
                unused_volume_percent = (volume_limit * truck_selection - volume_used) / volume_limit
                pallet_used = 0
                for so in values:
                    pallet = self.input_data.order_allocation_combinations[so]['pallet_spot']
                    pallet_used += np.round(self.raw_output_dict['order_allocation_dict'][so]) * pallet
                unused_pallet_percent = (pallet_limit * truck_selection - pallet_used) / pallet_limit

                unused_weight = weight_limit * truck_selection - weight_used
                unused_volume = volume_limit * truck_selection - volume_used
                unused_pallet = pallet_limit * truck_selection - pallet_used

                truck_lst.append([self.input_data.plan_id, self.dc, po, period, date, original_period, original_date, truck_selection,
                                  weight_limit, volume_limit, pallet_limit, original_weight_used, weight_used, original_volume_used, volume_used,
                                  original_pallet_used, pallet_used, unused_weight, unused_volume, unused_pallet,unused_weight_percent,unused_volume_percent,
                                  unused_pallet_percent])

            truck_df = pd.DataFrame(truck_lst, columns=['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                        'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                        'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                        'unused_volume_percent','unused_pallet_percent'])
            truck_df['flag'] = 'SolverResults'
            proposed_po_count = truck_df['truck_selection'].sum()

            if len(self.apo_truck_load_fully_utilized) > 0:

                fully_utilized = self.apo_truck_load_fully_utilized.groupby(['dc','po_number','requested_delivery_date','proposed_period','flag']).agg({'gross_weight': 'sum','volume': 'sum','pallet_spot': 'sum'}).reset_index()
                fully_utilized = pd.merge(fully_utilized,self.truck_details_fully_utilized,how='left',on=['dc','po_number','requested_delivery_date'])
                fully_utilized = fully_utilized[['dc', 'po_number', 'requested_delivery_date', 'proposed_period', 'flag','gross_weight', 'volume', 'pallet_spot', 'pallet_constraint','weight_constraint', 'volume_constraint']]

                fully_utilized = fully_utilized.rename(columns={'requested_delivery_date': 'date','proposed_period': 'period','gross_weight': 'weight_used','volume': 'volume_used',
                                                                'pallet_spot': 'pallet_used','weight_constraint': 'weight_limit','volume_constraint': 'volume_limit','pallet_constraint': 'pallet_limit'})
                fully_utilized['original_period'] = fully_utilized['period']
                fully_utilized['original_date'] = fully_utilized['date']
                fully_utilized['original_weight_used'] = fully_utilized['weight_used']
                fully_utilized['original_volume_used'] = fully_utilized['volume_used']
                fully_utilized['original_pallet_used'] = fully_utilized['pallet_used']
                fully_utilized['truck_selection'] = 1
                fully_utilized['unused_weight'] = fully_utilized['weight_limit'] - fully_utilized['weight_used']
                fully_utilized['unused_volume'] = fully_utilized['volume_limit'] - fully_utilized['volume_used']
                fully_utilized['unused_pallet'] = fully_utilized['pallet_limit'] - fully_utilized['pallet_used']
                fully_utilized['unused_weight_percent'] = (fully_utilized['weight_limit'] - fully_utilized['weight_used'])/fully_utilized['weight_limit']
                fully_utilized['unused_volume_percent'] = (fully_utilized['volume_limit'] - fully_utilized['volume_used'])/fully_utilized['volume_limit']
                fully_utilized['unused_pallet_percent'] = (fully_utilized['pallet_limit'] - fully_utilized['pallet_used'])/fully_utilized['pallet_limit']
                fully_utilized['scenario_id'] = self.input_data.plan_id
                fully_utilized = fully_utilized[['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                            'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                            'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                            'unused_volume_percent','unused_pallet_percent','flag']]
                con_truck_df = pd.concat([truck_df,fully_utilized])
            else:
                con_truck_df = truck_df

            if len(left_over_apo_truck_load) > 0 :

                left_over_po = left_over_apo_truck_load.groupby(['dc','proposed_po','proposed_requested_delivery_date','proposed_period','flag']).agg({'gross_weight': 'sum','volume': 'sum','pallet_spot': 'sum'}).reset_index()
                left_over_po = left_over_po.rename(columns={'proposed_po':'po_number','proposed_requested_delivery_date':'requested_delivery_date'})

                left_over_truck_capacity_details = self.input_data.input_tables_dict['left_over_truck_capacity_details']
                left_over_truck_capacity_details = left_over_truck_capacity_details.rename(columns={'requested_delivery_date':'original_date'})
                left_over_truck_capacity_details['original_period'] = left_over_truck_capacity_details["original_date"].apply(lambda x: self.input_data.date_to_period[x])

                left_over_po = pd.merge(left_over_po,left_over_truck_capacity_details,how='left',on=['dc','po_number'])
                left_over_po = left_over_po[['dc', 'po_number', 'requested_delivery_date', 'proposed_period', 'original_date','original_period',
                                             'flag','gross_weight', 'volume', 'pallet_spot', 'pallet_constraint','weight_constraint', 'volume_constraint']]

                left_over_po = left_over_po.rename(columns={'requested_delivery_date': 'date','proposed_period': 'period','gross_weight': 'weight_used','volume': 'volume_used',
                                                                'pallet_spot': 'pallet_used','weight_constraint': 'weight_limit','volume_constraint': 'volume_limit','pallet_constraint': 'pallet_limit'})

                left_over_po['original_weight_used'] = left_over_po['weight_used']
                left_over_po['original_volume_used'] = left_over_po['volume_used']
                left_over_po['original_pallet_used'] = left_over_po['pallet_used']
                left_over_po['truck_selection'] = 1
                left_over_po['unused_weight'] = left_over_po['weight_limit'] - left_over_po['weight_used']
                left_over_po['unused_volume'] = left_over_po['volume_limit'] - left_over_po['volume_used']
                left_over_po['unused_pallet'] = left_over_po['pallet_limit'] - left_over_po['pallet_used']
                left_over_po['unused_weight_percent'] = (left_over_po['weight_limit'] - left_over_po['weight_used'])/left_over_po['weight_limit']
                left_over_po['unused_volume_percent'] = (left_over_po['volume_limit'] - left_over_po['volume_used'])/left_over_po['volume_limit']
                left_over_po['unused_pallet_percent'] = (left_over_po['pallet_limit'] - left_over_po['pallet_used'])/left_over_po['pallet_limit']
                left_over_po['scenario_id'] = self.input_data.plan_id
                left_over_po = left_over_po[['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                            'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                            'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                            'unused_volume_percent','unused_pallet_percent','flag']]
                con_truck_df = pd.concat([con_truck_df,left_over_po])
                
            if len(left_over_apo_truck_load) == 0 and order_non_selection_dict:

                left_over_po_non_selected = non_selected_order_df.groupby(['dc','proposed_po','proposed_requested_delivery_date','proposed_period','flag']).agg({'gross_weight': 'sum','volume': 'sum','pallet_spot': 'sum'}).reset_index()
                left_over_po_non_selected = left_over_po_non_selected.rename(columns={'proposed_po':'po_number','proposed_requested_delivery_date':'requested_delivery_date'})

                left_over_truck_capacity_details_non_selected = self.input_data.input_tables_dict['left_over_truck_capacity_details']
                left_over_truck_capacity_details_non_selected = left_over_truck_capacity_details_non_selected.rename(columns={'requested_delivery_date':'original_date'})
                left_over_truck_capacity_details_non_selected['original_period'] = left_over_truck_capacity_details_non_selected["original_date"].apply(lambda x: self.input_data.date_to_period[x])

                left_over_po_non_selected = pd.merge(left_over_po_non_selected,left_over_truck_capacity_details_non_selected,how='left',on=['dc','po_number'])
                left_over_po_non_selected = left_over_po_non_selected[['dc', 'po_number', 'requested_delivery_date', 'proposed_period', 'original_date','original_period',
                                             'flag','gross_weight', 'volume', 'pallet_spot', 'pallet_constraint','weight_constraint', 'volume_constraint']]

                left_over_po_non_selected = left_over_po_non_selected.rename(columns={'requested_delivery_date': 'date','proposed_period': 'period','gross_weight': 'weight_used','volume': 'volume_used',
                                                                'pallet_spot': 'pallet_used','weight_constraint': 'weight_limit','volume_constraint': 'volume_limit','pallet_constraint': 'pallet_limit'})

                left_over_po_non_selected['original_weight_used'] = left_over_po_non_selected['weight_used']
                left_over_po_non_selected['original_volume_used'] = left_over_po_non_selected['volume_used']
                left_over_po_non_selected['original_pallet_used'] = left_over_po_non_selected['pallet_used']
                left_over_po_non_selected['truck_selection'] = 1
                left_over_po_non_selected['unused_weight'] = left_over_po_non_selected['weight_limit'] - left_over_po_non_selected['weight_used']
                left_over_po_non_selected['unused_volume'] = left_over_po_non_selected['volume_limit'] - left_over_po_non_selected['volume_used']
                left_over_po_non_selected['unused_pallet'] = left_over_po_non_selected['pallet_limit'] - left_over_po_non_selected['pallet_used']
                left_over_po_non_selected['unused_weight_percent'] = (left_over_po_non_selected['weight_limit'] - left_over_po_non_selected['weight_used'])/left_over_po_non_selected['weight_limit']
                left_over_po_non_selected['unused_volume_percent'] = (left_over_po_non_selected['volume_limit'] - left_over_po_non_selected['volume_used'])/left_over_po_non_selected['volume_limit']
                left_over_po_non_selected['unused_pallet_percent'] = (left_over_po_non_selected['pallet_limit'] - left_over_po_non_selected['pallet_used'])/left_over_po_non_selected['pallet_limit']
                left_over_po_non_selected['scenario_id'] = self.input_data.plan_id
                left_over_po_non_selected = left_over_po_non_selected[['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                            'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                            'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                            'unused_volume_percent','unused_pallet_percent','flag']]
                left_over_po_non_selected['flag'] = 'LeftOverAPOTruckLoad'
                con_truck_df = pd.concat([con_truck_df,left_over_po_non_selected])

            output_dict['truck_df'] = con_truck_df

            # Filtered Dataframe
            all_po = list(self.input_data.truck_po_level_details.keys())
            selected_df = con_truck_df[con_truck_df['truck_selection'] == 1].copy()
            selected_df['action'] = 'Selected'
            selected_po = selected_df['po_number'].unique().tolist()
            non_selected_po_master = list(set(all_po).difference(selected_po))
            non_selected_df = con_truck_df[(con_truck_df['po_number'].isin(non_selected_po_master)) & (con_truck_df['period'] == con_truck_df['original_period'])].copy()
            non_selected_df['action'] = 'Cancelled'
            non_selected_po = list(set(non_selected_po_master).difference(non_selected_df['po_number'].unique().tolist()))
            non_selected_df2 = pd.DataFrame(non_selected_po,columns=['po_number'])
            non_selected_df2['scenario_id'] = self.input_data.plan_id
            non_selected_df2['dc'] = self.dc
            non_selected_df2['action'] = 'Cancelled'
            non_selected_df2['flag'] = 'Not Validate'
            non_selected_df2["original_date"] = non_selected_df2["po_number"].apply(lambda x: self.input_data.truck_po_level_details.get(x, {}).get('requested_delivery_date'))
            sel_non_sel_df = pd.concat([selected_df,non_selected_df,non_selected_df2])
            sel_non_sel_df['scenario_name'] = 'stage_one'
            sel_non_sel_df = sel_non_sel_df[['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period','original_date', 'truck_selection', 'weight_limit', 'volume_limit',
             'pallet_limit', 'original_weight_used', 'weight_used','original_volume_used', 'volume_used', 'original_pallet_used',
             'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet','unused_weight_percent', 'unused_volume_percent',
             'unused_pallet_percent','flag','action','scenario_name']]
            output_dict['sel_non_sel_df'] = sel_non_sel_df

            logger.info("Truck Details Solution DataFrame Created")

        except Exception as e:
            logger.warning("Truck Details Solution DataFrame missing or empty " + str(e))
            logger.warning(f"Result: {traceback.format_exc()}")
            proposed_po_count, proposed_under_utilization_range_count = None, None
            truck_df = pd.DataFrame(columns=['scenario_id', 'dc','po_number', 'period','date', 'original_period','original_date','truck_selection',
                                                        'weight_limit', 'volume_limit', 'pallet_limit','original_weight_used','weight_used', 'original_volume_used','volume_used',
                                                        'original_pallet_used','pallet_used','unused_weight','unused_volume','unused_pallet','unused_weight_percent',
                                                        'unused_volume_percent','unused_pallet_percent','truck_under_utilization','truck_under_utilization_range_trigger','unused_weight_percent_solver',
                                                        'unused_volume_percent_solver', 'unused_pallet_percent_solver','flag'])

            sel_non_sel_df = pd.DataFrame(columns=['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period','original_date', 'truck_selection', 'weight_limit', 'volume_limit',
             'pallet_limit', 'original_weight_used', 'weight_used','original_volume_used', 'volume_used', 'original_pallet_used',
             'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet','unused_weight_percent', 'unused_volume_percent',
             'unused_pallet_percent', 'truck_under_utilization','truck_under_utilization_range_trigger', 'unused_weight_percent_solver',
             'unused_volume_percent_solver', 'unused_pallet_percent_solver', 'flag','action','scenario_name'])
            output_dict['truck_df'] = truck_df
            output_dict['sel_non_sel_df'] = sel_non_sel_df
            logger.warning("Truck Details Solution DataFrame Empty")

        return output_dict, proposed_po_count


