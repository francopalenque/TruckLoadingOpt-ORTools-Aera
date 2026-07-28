import pandas as pd
import numpy as np
import os
import traceback
from src.common.logger_config import logger


def generate_final_item_recommendations(final_flags_df_item, solver_reject_item_df):
    """
    Post-process item-level recommendations based on all scenarios
    """
    try:
        max_item_result = final_flags_df_item.groupby('sales_document')['sales_document_item'].apply(
            lambda x: x.astype(int).max()).reset_index()
        # --- Merge solver reject qty ---
        df = final_flags_df_item.merge(
            solver_reject_item_df,
            on=["sales_document", "sales_document_item", "material"],
            how="left"
        )
        df["solver_reject_pallet"] = df["solver_reject_pallet"].fillna(0)
        df["solver_reject_volume"] = df["solver_reject_volume"].fillna(0)
        df["solver_reject_gross_weight"] = df["solver_reject_gross_weight"].fillna(0)
        df["solver_reject_cfrm_qty"] = df["solver_reject_cfrm_qty"].fillna(0)
        df["solver_reject_ord_qty"] = df["solver_reject_ord_qty"].fillna(0)

        final_rows = []

        for _, row in df.iterrows():

            try:

                order_x = row.get("order_quantity_in_base_unit_x", 0) or 0
                confirmed_y = row.get("confirmed_quantity_in_base_unit_y", 0) or 0
                confirmed_x = row.get("confirmed_quantity_in_base_unit_x", 0) or 0
                solver_reject_qty = row.get("solver_reject_cfrm_qty", 0) or 0
                solver_reject_pal = row.get("solver_reject_pallet", 0) or 0
                solver_reject_weight = row.get("solver_reject_gross_weight", 0) or 0
                solver_reject_vol = row.get("solver_reject_volume", 0) or 0
                recomm_type = row.get("recommendation_type", 'Not Set') or 'Not Set'

                current_item = int(row["sales_document_item"])

                # ----------------------------
                # Scenario 1: No Change
                # ----------------------------
                if solver_reject_qty == 0:
                    final_rows.append(row)
                    continue

                # ----------------------------
                # Scenario 2: Full Reject
                # ----------------------------
                if (
                        pd.isna(confirmed_y) or confirmed_y == 0) and solver_reject_qty == order_x and recomm_type == 'Reject Order Line':
                    print('scenario - 2 -----')
                    print(
                        f"confirmed_y: {confirmed_y}, solver_reject_qty: {solver_reject_qty}, order_x: {order_x}, recomm_type: {recomm_type}")
                    reject_row = row.copy()
                    reject_row["input_flag"] = 0
                    reject_row["generated_flag"] = 0
                    final_rows.append(reject_row)
                    continue

                # ----------------------------
                # Scenario 3 & 4 - complete order rejected but because of 2 reasons - optimizer ignored and line moved to another PO
                # ----------------------------
                if (
                        pd.isna(confirmed_y) or confirmed_y == 0) and solver_reject_qty != order_x and recomm_type == 'Reject Order Line':
                    print('scenario - 3 & 4 -----')
                    print(confirmed_y, solver_reject_qty, order_x)

                    retained_qty = order_x - solver_reject_qty

                    # Row 1: Update
                    update_row = row.copy()
                    update_row["confirmed_quantity_in_base_unit_y"] = retained_qty
                    update_row["recommendation_type"] = "Update Order Line"
                    update_row["input_flag"] = 1
                    update_row["output_flag"] = 1
                    update_row["update_flag"] = 1
                    update_row["generated_flag"] = 0
                    final_rows.append(update_row)

                    # Row 2: Reject same item
                    reject_same = row.copy()
                    reject_same["order_quantity_in_base_unit_x"] = retained_qty
                    reject_same["confirmed_quantity_in_base_unit_x"] = retained_qty
                    reject_same["confirmed_quantity_in_base_unit_y"] = np.nan
                    reject_same["recommendation_type"] = "Reject Order Line"
                    reject_same["input_flag"] = 1
                    reject_same["output_flag"] = 0
                    reject_same["generated_flag"] = 0
                    final_rows.append(reject_same)

                    max_item = int(max_item_result.loc[max_item_result['sales_document'] == row[
                        "sales_document"], 'sales_document_item'].iloc[0])

                    # --- Create Row ---
                    create_row = row.copy()
                    create_row["recommendation_type"] = "Create Order Line"
                    create_row["confirmed_quantity_in_base_unit_y"] = solver_reject_qty
                    create_row["pallet_spot_y"] = solver_reject_pal
                    create_row["volume_y"] = solver_reject_vol
                    create_row["gross_weight_y"] = solver_reject_weight
                    create_row["order_quantity_in_base_unit_y"] = 0
                    create_row["confirmed_quantity_in_base_unit_x"] = np.nan
                    create_row["pallet_spot_x"] = np.nan
                    create_row["volume_x"] = np.nan
                    create_row["gross_weight_x"] = np.nan
                    create_row["order_quantity_in_base_unit_x"] = np.nan
                    create_row["input_flag"] = 0
                    create_row["output_flag"] = 0
                    create_row["update_flag"] = 0
                    create_row["generated_flag"] = 0
                    create_row["sales_document_item"] = str(max_item + 10)
                    final_rows.append(create_row)

                    # --- Reject Row ---
                    reject_row = create_row.copy()
                    reject_row["recommendation_type"] = "Reject Order Line"
                    reject_row["input_flag"] = 0
                    reject_row["output_flag"] = 0
                    reject_row["update_flag"] = 0
                    reject_row["generated_flag"] = 0
                    reject_row["confirmed_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["pallet_spot_x"] = solver_reject_pal
                    reject_row["volume_x"] = solver_reject_vol
                    reject_row["gross_weight_x"] = solver_reject_weight
                    reject_row["order_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["confirmed_quantity_in_base_unit_y"] = np.nan
                    reject_row["pallet_spot_y"] = np.nan
                    reject_row["volume_y"] = np.nan
                    reject_row["gross_weight_y"] = np.nan
                    reject_row["order_quantity_in_base_unit_y"] = np.nan
                    final_rows.append(reject_row)

                    max_item_result.loc[max_item_result['sales_document'] == row[
                        "sales_document"], 'sales_document_item'] = max_item + 10
                    continue

                # ----------------------------
                # Scenario 5 - If net quantity unchanged but solver rejected exists, keep item as Not Set and separately reject solver quantity.
                # ----------------------------
                if solver_reject_qty > 0 and order_x == confirmed_y:
                    print('scenario - 5 -----')
                    print(confirmed_y, solver_reject_qty, order_x)

                    # Row 1: Not Set
                    final_rows.append(row)

                    reject_row = row.copy()
                    reject_row["recommendation_type"] = "Reject Order Line"
                    reject_row["input_flag"] = 0
                    reject_row["output_flag"] = 0
                    reject_row["update_flag"] = 0
                    reject_row["generated_flag"] = 0
                    reject_row["confirmed_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["pallet_spot_x"] = solver_reject_pal
                    reject_row["volume_x"] = solver_reject_vol
                    reject_row["gross_weight_x"] = solver_reject_weight
                    reject_row["order_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["confirmed_quantity_in_base_unit_y"] = np.nan
                    reject_row["pallet_spot_y"] = np.nan
                    reject_row["volume_y"] = np.nan
                    reject_row["gross_weight_y"] = np.nan
                    reject_row["order_quantity_in_base_unit_y"] = np.nan
                    final_rows.append(reject_row)

                    continue

                # ----------------------------
                # Scenario 6 & 7 - Partial Reduction + Solver Reject
                # ----------------------------
                if solver_reject_qty > 0 and order_x != confirmed_y:
                    print('scenario - 6 & 7 -----')
                    print(
                        f"confirmed_y: {confirmed_y}, solver_reject_qty: {solver_reject_qty}, order_x: {order_x}, recomm_type: {recomm_type}")
                    # Row 1: Update
                    update_row = row.copy()
                    update_row["recommendation_type"] = "Update Order Line"
                    update_row["input_flag"] = 1
                    update_row["output_flag"] = 1
                    update_row["update_flag"] = 1
                    final_rows.append(update_row)

                    # Row 2: Solver Reject
                    reject_row = row.copy()
                    reject_row["recommendation_type"] = "Reject Order Line"
                    reject_row["input_flag"] = 0
                    reject_row["output_flag"] = 0
                    reject_row["update_flag"] = 0
                    reject_row["generated_flag"] = 0
                    reject_row["confirmed_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["pallet_spot_x"] = solver_reject_pal
                    reject_row["volume_x"] = solver_reject_vol
                    reject_row["gross_weight_x"] = solver_reject_weight
                    reject_row["order_quantity_in_base_unit_x"] = solver_reject_qty
                    reject_row["confirmed_quantity_in_base_unit_y"] = np.nan
                    reject_row["pallet_spot_y"] = np.nan
                    reject_row["volume_y"] = np.nan
                    reject_row["gross_weight_y"] = np.nan
                    reject_row["order_quantity_in_base_unit_y"] = np.nan
                    final_rows.append(reject_row)

                    continue

                # ----------------------------
                # Default fallback
                # ----------------------------
                final_rows.append(row)
            except Exception as row_error:
                # Skip only this row
                logger.warning(f"Skipping row due to error: {row_error}")
                continue

        return pd.DataFrame(final_rows)

    except Exception as e:
        # Fail-safe fallback
        logger.warning(f"Error in generate_final_item_recommendations: {e}")
        return final_flags_df_item


def create_and_reject_for_partial_updates(df):
    """
    For DC+Material groups with only one Update recommendation where
    order_qty_x > confirmed_qty_y, create a new Create+Reject pair for leftover quantity.
    """
    df = df.copy()
    new_rows = []

    valid_df = df[df["recommendation_type"] != "Not Set"]
    # Base info
    # max_item = (
    #     df[df["sales_document"] == row["sales_document"]]["sales_document_item"]
    #     .astype(int)
    #     .max()
    # )
    # max_item_result = df.groupby('sales_document')['sales_document_item'].max().reset_index()
    max_item_result = df.groupby('sales_document')['sales_document_item'].apply(
        lambda x: x.astype(int).max()).reset_index()

    for (dc, material), group in valid_df.groupby(["dc", "material"]):
        # Single recommendation in this group
        try:
            if len(group) == 1:

                row = group.iloc[0]
                if row["recommendation_type"] == "Update Order Line":
                    if row["order_quantity_in_base_unit_x"] > row["confirmed_quantity_in_base_unit_y"]:
                        try:
                            df.loc[row.name, "generated_flag"] = 1
                        except Exception as e:
                            logger.warning(f"Warning: could not set generated_flag on original row: {e}")
                        leftover_qty = (
                                row["order_quantity_in_base_unit_x"] - row["confirmed_quantity_in_base_unit_y"]
                        )

                        diff_pallet_spot = row["pallet_spot_x"] - row["pallet_spot_y"]
                        diff_volume = row["volume_x"] - row["volume_y"]
                        diff_weight = row["gross_weight_x"] - row["gross_weight_y"]

                        # # Base info
                        # max_item = (
                        #     df[df["sales_document"] == row["sales_document"]]["sales_document_item"]
                        #     .astype(int)
                        #     .max()
                        # )
                        max_item = int(max_item_result.loc[max_item_result['sales_document'] == row[
                            "sales_document"], 'sales_document_item'].iloc[0])
                        # --- Create Row ---
                        create_row = row.copy()
                        create_row["recommendation_type"] = "Create Order Line"
                        create_row["confirmed_quantity_in_base_unit_y"] = leftover_qty
                        create_row["pallet_spot_y"] = diff_pallet_spot
                        create_row["volume_y"] = diff_volume
                        create_row["gross_weight_y"] = diff_weight
                        create_row["order_quantity_in_base_unit_y"] = 0
                        create_row["confirmed_quantity_in_base_unit_x"] = np.nan
                        create_row["pallet_spot_x"] = np.nan
                        create_row["volume_x"] = np.nan
                        create_row["gross_weight_x"] = np.nan
                        create_row["order_quantity_in_base_unit_x"] = np.nan
                        create_row["input_flag"] = 0
                        create_row["output_flag"] = 0
                        create_row["update_flag"] = 0
                        create_row["generated_flag"] = 1
                        create_row["sales_document_item"] = str(max_item + 10)

                        # --- Reject Row ---
                        reject_row = create_row.copy()
                        reject_row["recommendation_type"] = "Reject Order Line"
                        reject_row["input_flag"] = 0
                        reject_row["output_flag"] = 0
                        reject_row["update_flag"] = 0
                        reject_row["generated_flag"] = 1
                        reject_row["confirmed_quantity_in_base_unit_x"] = leftover_qty
                        reject_row["pallet_spot_x"] = diff_pallet_spot
                        reject_row["volume_x"] = diff_volume
                        reject_row["gross_weight_x"] = diff_weight
                        reject_row["order_quantity_in_base_unit_x"] = leftover_qty
                        reject_row["confirmed_quantity_in_base_unit_y"] = np.nan
                        reject_row["pallet_spot_y"] = np.nan
                        reject_row["volume_y"] = np.nan
                        reject_row["gross_weight_y"] = np.nan
                        reject_row["order_quantity_in_base_unit_y"] = np.nan

                        # Add both rows in order: Create → Reject
                        new_rows.extend([create_row, reject_row])
                        # max_item = max_item+10
                        max_item_result.loc[max_item_result['sales_document'] == row[
                            "sales_document"], 'sales_document_item'] = max_item + 10
        except Exception as e:
            logger.warning(f"Error in create_and_reject_for_partial_updates for {material}, {dc}: {e}")

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    return df


def assign_so_and_schedule_lines(merged_df, input_df):
    try:

        df = merged_df.copy()
        # Always align sales_document to input_df
        base_sales_doc = input_df["sales_document"].iloc[0]
        # Track max SO item from input
        max_so_item = input_df["sales_document_item"].astype(int).max()
        # Process only rows that need to be created
        create_mask = (df["output_flag"] == 1) & (df["input_flag"] == 0)
        create_rows = df[create_mask]
        if create_rows.empty:
            return df

        # Group by material to handle multiple rows per material
        for (material, material_by_customer), group in create_rows.groupby(["material","materialbycustomer"]):

            # material_subset = input_df[input_df["material"] == material]
            material_subset = input_df[(input_df[
                                            "material"] == material) & (input_df["materialbycustomer"] == material_by_customer)]  # & (input_df.get("input_flag", 0) == 1)] #we will not have input_flag in input_df

            if not material_subset.empty:

                # Material exists → reuse SO item

                so_item = material_subset["sales_document_item"].iloc[0]
                max_sched = material_subset["schedule_line"].astype(int).max()

                # Assign new schedule lines incrementally

                new_scheds = list(range(max_sched + 1, max_sched + 1 + len(group)))
                new_scheds = [str(s) for s in new_scheds]
                df.loc[group.index, "sales_document"] = base_sales_doc
                df.loc[group.index, "sales_document_item"] = so_item
                df.loc[group.index, "schedule_line"] = new_scheds
                df.loc[group.index, ["input_flag", "output_flag"]] = [0, 1]

            else:
                # New material → assign new SO item
                max_so_item += 10
                so_item = str(max_so_item)
                new_scheds = list(range(1, len(group) + 1))
                new_scheds = [str(s) for s in new_scheds]
                df.loc[group.index, "sales_document"] = base_sales_doc
                df.loc[group.index, "sales_document_item"] = so_item
                df.loc[group.index, "schedule_line"] = new_scheds
                df.loc[group.index, ["input_flag", "output_flag"]] = [0, 1]

        return df

    except Exception as e:
        logger.warning(f"Error in assign_so_and_schedule_lines: {e}")
        logger.warning(f"Result: {traceback.format_exc()}")
        return merged_df


def aggregate_to_item_level(df, sum_cols, qty_input_col, qty_output_col):
    """

    Aggregate schedule line level recommendations to item level,

    respecting input/output flags and checking quantities for update_flag.

    """

    try:

        result_rows = []

        # Group at item level

        group_keys = ["sales_document", "sales_document_item", "material"]

        for keys, group in df.groupby(group_keys):

            update_flag = 0
            flag_combos = set(zip(group["input_flag"], group["output_flag"]))
            # Case A: only input

            if flag_combos == {(1, 0)}:
                agg_vals = group[sum_cols].sum(min_count=1)
                input_flag, output_flag = 1, 0

            # Case B: only output

            elif flag_combos == {(0, 1)}:
                agg_vals = group[sum_cols].sum(min_count=1)
                input_flag, output_flag = 0, 1

            # Case C: mix input-only & output-only

            elif flag_combos.issuperset({(1, 0), (0, 1)}):
                input_only = group[(group["input_flag"] == 1) & (group["output_flag"] == 0)][sum_cols].sum(
                    min_count=1).fillna(0)
                output_only = group[(group["input_flag"] == 0) & (group["output_flag"] == 1)][sum_cols].sum(
                    min_count=1).fillna(0)
                agg_vals = output_only + input_only
                input_flag, output_flag = 1, 1
                # quantity check

                if agg_vals[qty_input_col] != agg_vals[qty_output_col]:
                    update_flag = 1

            # Case D: all both (1,1)

            else:

                agg_vals = group[sum_cols].sum(min_count=1)
                input_flag, output_flag = 1, 1
                # quantity check
                if agg_vals[qty_input_col] != agg_vals[qty_output_col]:
                    update_flag = 1
                    if agg_vals[qty_output_col]== 0 and len(group)==1 and (group['proposed_po']==group['po_number']).all():
                        update_flag = 0

            # Build result row

            # row = {col: group[col].iloc[0] for col in group.columns if
            #        col not in sum_cols + ["input_flag", "output_flag", "update_flag"]}
            # Take non-null values from within the group
            row = {}
            for col in group.columns:
                if col in sum_cols + ["input_flag", "output_flag", "update_flag"]:
                    continue
                non_null_values = group[col].dropna().unique()
                if len(non_null_values) == 1:
                    row[col] = non_null_values[0]
                elif len(non_null_values) > 1:
                    # Prefer non-null from output_flag=1 row if conflict
                    output_rows = group[group["output_flag"] == 1]
                    val = output_rows[col].dropna().iloc[0] if not output_rows.empty and pd.notna(
                        output_rows[col].iloc[0]) else non_null_values[0]
                    row[col] = val
                else:
                    row[col] = None
            for col in sum_cols:
                row[col] = round(agg_vals[col], 2)

            row["input_flag"] = input_flag
            row["output_flag"] = output_flag
            row["update_flag"] = update_flag
            result_rows.append(row)
        return pd.DataFrame(result_rows)

    except Exception as e:
        logger.warning(f"Error in aggregate_to_item_level: {e}")
        return df


# ------------------ Recommendation Logic ------------------ #

def get_recommendation(row):
    """Assigns recommendation based on update/input/output flags."""

    try:

        if row["update_flag"] == 1:
            return "Update Order Line"
        elif row["input_flag"] == 1 and row["output_flag"] == 0:
            return "Reject Order Line"
        elif row["input_flag"] == 0 and row["output_flag"] == 1:
            return "Create Order Line"
        else:
            return "Not Set"

    except Exception as e:
        logger.warning(f"Error in get_recommendation: {e}")
        return "Not Set"


def merge_and_flag(input_keys, output_keys, dc, proposed_po, cols, input_col):
    try:

        merged = pd.merge(
            input_keys.assign(input_flag=1),
            output_keys.assign(output_flag=1),
            on=cols,
            how="outer"
        ).fillna({"input_flag": 0, "output_flag": 0})

        sum_cols = ["pallet_spot_y", "gross_weight_y", "volume_y", "confirmed_quantity_in_base_unit_y"]
        group_cols = [col for col in merged.columns if col not in sum_cols]

        merged = (
            merged.groupby(group_cols, dropna=False, as_index=False)[sum_cols]
            .sum(min_count=1)  # preserves NaN if all are NaN
        )

        merged[["pallet_spot_y", "gross_weight_y", "volume_y", "confirmed_quantity_in_base_unit_y"]] = merged[
            ["pallet_spot_y", "gross_weight_y", "volume_y", "confirmed_quantity_in_base_unit_y"]].round(2)

        merged["input_flag"] = merged["input_flag"].astype(int)
        merged["output_flag"] = merged["output_flag"].astype(int)
        merged["update_flag"] = 0
        both_mask = (merged["input_flag"] == 1) & (merged["output_flag"] == 1)
        merged.loc[both_mask & (merged[input_col] != merged["confirmed_quantity_in_base_unit_y"]), "update_flag"] = 1
        merged["dc"] = dc
        merged["proposed_po"] = proposed_po

        return merged

    except Exception as e:
        logger.warning(f"Error in merge_and_flag for dc={dc}, proposed_po={proposed_po}: {e}")
        return pd.DataFrame()


class PostProcessorAnalysis:

    def __init__(self, input_tables_dict, finial_output_stage_two, output_path):

        self.input_tables_dict = input_tables_dict
        self.finial_output_stage_two = finial_output_stage_two
        self.output_path = output_path

    def results(self):
        self.post_process_analysis()

    def post_process_analysis(self):

        input_df = self.input_tables_dict['original_apo_truck_load']
        output_df_lst = self.finial_output_stage_two['finial_order_df']
        output_df = pd.concat(output_df_lst)
        df_solver_reject = output_df[(output_df['flag'] == 'Solver Rejected Line') &    (output_df['proposed_po'].isna())][
            ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material', 'materialbycustomer',
             'po_number', 'dc', 'dc_name', 'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit',
             'order_quantity_in_base_unit', 'volume', 'requested_delivery_date', 'base_unit', 'order_quantity_unit',
             'atp_availability_date', 'delivery_date']].drop_duplicates().reset_index(drop=True)
        df_solver_reject_leftover = output_df[(output_df['flag'] == 'Solver Rejected Line') &    (output_df['proposed_po'].notna())]
        output_df = output_df[output_df['order_allocation'] > 0]
        output_df = pd.concat([output_df, df_solver_reject_leftover],ignore_index=True).drop_duplicates()
        output_csv = "output_schedule_line.csv"
        output_item_csv = "output_item.csv"

        df_solver_reject = df_solver_reject.astype({
            "sales_document": "string",
            "sales_document_item": "string",
            "schedule_line": "string",
            "material": "string",
            "materialbycustomer": "string"
        })

        input_df = input_df.astype({
            "sales_document": "string",
            "sales_document_item": "string",
            "schedule_line": "string",
            "material": "string",
            "materialbycustomer": "string"
        })
        output_df = output_df.astype({
            "sales_document": "string",
            "sales_document_item": "string",
            "schedule_line": "string",
            "material": "string",
            "materialbycustomer": "string"
        })
        # output_df['materialbycustomer'] = output_df['materialbycustomer'].str.zfill(18)
        # input_df['materialbycustomer'] = input_df['materialbycustomer'].str.zfill(18)
        output_df['material'] = output_df['material'].str.zfill(18)
        input_df['material'] = input_df['material'].str.zfill(18)
        df_solver_reject['material'] = df_solver_reject['material'].str.zfill(18)

        try:
            all_results = []
            all_results_item = []
            for (dc, proposed_po), output_subset in output_df.groupby(["dc", "proposed_po"]):

                try:
                    input_subset = input_df[(input_df["dc"] == dc) & (input_df["po_number"] == proposed_po)]

                    input_subset = input_subset[[
                        "sales_document", "sales_document_item", "schedule_line",
                        "material", "materialbycustomer", "confirmed_quantity_in_base_unit",
                        "order_quantity_in_base_unit", "pallet_spot", "gross_weight", "volume",
                        "requested_delivery_date", "dc_name", "base_unit", "order_quantity_unit",
                        "atp_availability_date", "delivery_date", "priority_line_flag"
                    ]]
                    output_subset = output_subset[[
                        "scenario_id", 'sales_document', 'sales_document_item', 'schedule_line',
                        'material', 'po_number', 'dc', 'dc_name', 'pallet_spot', 'gross_weight',
                        'confirmed_quantity_in_base_unit', 'volume', 'requested_delivery_date',
                        'atp_availability_date', 'actual_delivery_date', 'original_delivery_date', 'proposed_po',
                        'proposed_requested_delivery_date', 'base_unit', 'order_quantity_unit',
                        'order_quantity_in_base_unit',
                        'materialbycustomer', 'scenario_name', "priority_line_flag"
                    ]]
                    output_subset = output_subset.rename(columns={"actual_delivery_date": "delivery_date"})

                    join_on_cols_schedule_line = ["sales_document", "sales_document_item", "schedule_line", "material",
                                                  "materialbycustomer"]
                    merged = merge_and_flag(input_subset, output_subset, dc, proposed_po, join_on_cols_schedule_line,
                                            "confirmed_quantity_in_base_unit_x")

                    cleaned_merged = assign_so_and_schedule_lines(merged, input_subset)

                    merged_item = aggregate_to_item_level(cleaned_merged.drop(
                        columns=['schedule_line', 'atp_availability_date_x', 'delivery_date_x',
                                 'atp_availability_date_y',
                                 'delivery_date_y', 'original_delivery_date', 'priority_line_flag_x',
                                 'priority_line_flag_y']),
                        ["volume_y", "confirmed_quantity_in_base_unit_y",
                         "order_quantity_in_base_unit_y", "pallet_spot_y",
                         "gross_weight_y", "volume_x",
                         "confirmed_quantity_in_base_unit_x",
                         "order_quantity_in_base_unit_x", "pallet_spot_x",
                         "gross_weight_x"], 'order_quantity_in_base_unit_x',
                        'confirmed_quantity_in_base_unit_y')

                    all_results.append(cleaned_merged)
                    all_results_item.append(merged_item)

                except Exception as inner_e:
                    logger.warning(f"Error processing dc={dc}, proposed_po={proposed_po}: {inner_e}")
                    continue

            if not all_results:
                logger.warning("No results generated.")
                return

            final_flags_df = pd.concat(all_results, ignore_index=True)
            final_flags_df["recommendation_type"] = final_flags_df.apply(get_recommendation, axis=1)
            final_flags_df["date_change_flag"] = np.where(
                (final_flags_df["requested_delivery_date_y"].notna()) &
                (final_flags_df["proposed_requested_delivery_date"].notna()) &
                (final_flags_df["requested_delivery_date_y"] != final_flags_df["proposed_requested_delivery_date"]),
                1,
                0
            )

            final_flags_df_item = pd.concat(all_results_item, ignore_index=True)
            final_flags_df_item["recommendation_type"] = final_flags_df_item.apply(get_recommendation, axis=1)
            final_flags_df_item["date_change_flag"] = np.where(
                (final_flags_df_item["requested_delivery_date_y"].notna()) &
                (final_flags_df_item["proposed_requested_delivery_date"].notna()) &
                (final_flags_df_item["requested_delivery_date_y"] != final_flags_df_item[
                    "proposed_requested_delivery_date"]),
                1,
                0
            )

            try:
                final_flags_df_item["generated_flag"] = 0
                col = "scenario_id"
                column_seq = ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material',
                              'materialbycustomer', 'confirmed_quantity_in_base_unit_x',
                              'order_quantity_in_base_unit_x', 'pallet_spot_x', 'gross_weight_x',
                              'volume_x', 'po_number', 'dc', 'proposed_po',
                              'proposed_requested_delivery_date', 'pallet_spot_y', 'gross_weight_y',
                              'volume_y', 'confirmed_quantity_in_base_unit_y', 'recommendation_type',
                              'date_change_flag', 'requested_delivery_date_x', 'requested_delivery_date_y',
                              'delivery_date_x', 'delivery_date_y', 'original_delivery_date', 'atp_availability_date_x',
                              'atp_availability_date_y', 'dc_name_x', 'dc_name_y',
                              'base_unit_x', 'base_unit_y', 'order_quantity_unit_x', 'order_quantity_unit_y',
                              'order_quantity_in_base_unit_y', 'scenario_name', 'priority_line_flag_x',
                              'priority_line_flag_y', 'input_flag', 'output_flag', 'update_flag']
                column_seq_item = ['scenario_id', 'sales_document', 'sales_document_item', 'material',
                                   'materialbycustomer', 'po_number', 'dc', 'proposed_po',
                                   'proposed_requested_delivery_date', 'volume_y', 'confirmed_quantity_in_base_unit_y',
                                   'pallet_spot_y', 'gross_weight_y', 'volume_x', 'confirmed_quantity_in_base_unit_x',
                                   'order_quantity_in_base_unit_x', 'pallet_spot_x', 'gross_weight_x',
                                   'recommendation_type', 'date_change_flag',
                                   'requested_delivery_date_x', 'requested_delivery_date_y', 'dc_name_x', 'dc_name_y',
                                   'base_unit_x', 'base_unit_y', 'order_quantity_unit_x', 'order_quantity_unit_y',
                                   'order_quantity_in_base_unit_y', 'scenario_name', 'input_flag', 'output_flag',
                                   'update_flag', 'generated_flag']
                final_flags_df_item = create_and_reject_for_partial_updates(final_flags_df_item)
                if len(df_solver_reject) > 0:
                    solver_reject_item_df = df_solver_reject.drop(
                        columns=['atp_availability_date', 'delivery_date', 'scenario_id', 'schedule_line',
                                 'materialbycustomer', 'po_number', 'dc', 'dc_name', 'requested_delivery_date',
                                 'base_unit', 'order_quantity_unit'])
                    # Group by all columns except the ones to aggregate, and sum pallet, volume, weight
                    groupby_cols = [col for col in solver_reject_item_df.columns if
                                    col not in ['pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit',
                                                'order_quantity_in_base_unit', 'volume']]
                    solver_reject_item_df = solver_reject_item_df.groupby(groupby_cols, as_index=False).agg({
                        'pallet_spot': 'sum',
                        'volume': 'sum',
                        'gross_weight': 'sum',
                        'confirmed_quantity_in_base_unit': 'sum',
                        'order_quantity_in_base_unit': 'sum'
                    }).rename(columns={
                        "pallet_spot": "solver_reject_pallet",
                        "volume": "solver_reject_volume",
                        "gross_weight": "solver_reject_gross_weight",
                        "confirmed_quantity_in_base_unit": "solver_reject_cfrm_qty",
                        "order_quantity_in_base_unit": "solver_reject_ord_qty"
                    })
                    final_flags_df_item = generate_final_item_recommendations(final_flags_df_item,
                                                                              solver_reject_item_df)
                final_flags_df = final_flags_df[column_seq]
                final_flags_df_item = final_flags_df_item[column_seq_item]
                final_flags_df_item.to_csv(os.path.join(self.output_path, output_item_csv), index=False)
                final_flags_df.to_csv(os.path.join(self.output_path, output_csv), index=False)

                logger.info(f"Final result saved to {output_csv}")

            except Exception as e:
                logger.warning(f"Error saving output file {output_csv}: {e}")

        except Exception as e:
            logger.warning(f"Error in main: {e}")


class InputPostProcessor:
    def __init__(self, input_data_dict, plan_id, apo_truck_load_fully_utilized, truck_details_fully_utilized, dc):
        self.input_data_dict = input_data_dict
        self.plan_id = plan_id
        self.apo_truck_load_fully_utilized = apo_truck_load_fully_utilized
        self.truck_details_fully_utilized = truck_details_fully_utilized
        self.dc = dc

        self.output_dict = None
        self.actual_lines = None

    def results(self):
        self.output_dict = self.post_process_results()


    def post_process_results(self):
        output_dict = {}
        logger.info("Creating Solution DataFrames")

        # Order DataFrame
        try:
            logger.info("Creating Order DataFrame")

            column_seq = ['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material','po_number', 'dc', 'dc_name',
                          'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume', 'requested_delivery_date', 'atp_availability_date', 'delivery_date', 'original_delivery_date',
                          'actual_delivery_date', 'requested_delivery_period', 'delivery_period', 'requested_delivery_day_name',
                          'delivery_day_name', 'proposed_po', 'proposed_period', 'shuffle_together_flag',
                          'proposed_requested_delivery_date', 'order_allocation', 'flag', 'priority_line_flag',
                          'units_per_pallet', 'weight_per_unit', 'volume_per_unit',
                          'base_unit', 'order_creation_date', 'order_quantity_unit', 'planned_goods_issue_date',
                          'order_quantity_in_base_unit', 'pallet_spot_conversion_factor', 'materialbycustomer']

            if len(self.apo_truck_load_fully_utilized) > 0:
                con_finial_order_df = pd.concat([self.input_data_dict['apo_truck_load'], self.apo_truck_load_fully_utilized])
            else:
                con_finial_order_df = self.input_data_dict['apo_truck_load'].copy()
            con_finial_order_df = con_finial_order_df.reset_index(drop=True)
            self.actual_lines = len(con_finial_order_df)
            con_finial_order_df['proposed_po'] = con_finial_order_df['po_number']
            con_finial_order_df['proposed_requested_delivery_date'] = con_finial_order_df['requested_delivery_date']
            con_finial_order_df['order_allocation'] = 1
            con_finial_order_df['scenario_id'] = self.plan_id
            con_finial_order_df["requested_delivery_period"] = None
            con_finial_order_df["delivery_period"] = None
            con_finial_order_df['proposed_period'] = con_finial_order_df['requested_delivery_period']
            con_finial_order_df['original_delivery_date'] = con_finial_order_df['delivery_date']
            con_finial_order_df['flag'] = 'DirectlyFromInput'
            con_finial_order_df = con_finial_order_df.rename(columns={'pallet_conversion_factor': 'units_per_pallet', 'weight_conversion_factor': 'weight_per_unit', 'volume_conversion_factor': 'volume_per_unit'})
            con_finial_order_df = con_finial_order_df[column_seq]
            con_finial_order_df['delivery_date_check_flag'] = np.where(con_finial_order_df['proposed_period'] >= con_finial_order_df['delivery_period'], True, False)
            con_finial_order_df['weight_check_flag'] = None
            con_finial_order_df['volume_check_flag'] = None
            con_finial_order_df['pallet_check_flag'] = None
            con_finial_order_df['r_type'] = None
            con_finial_order_df['scenario_name'] = 'DirectlyFromInput'
            con_finial_order_df = con_finial_order_df[['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material', 'po_number', 'dc',
                 'dc_name','pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume', 'requested_delivery_date',
                 'atp_availability_date', 'delivery_date', 'original_delivery_date', 'actual_delivery_date',
                 'requested_delivery_period', 'delivery_period', 'requested_delivery_day_name', 'delivery_day_name',
                 'proposed_po', 'proposed_period', 'proposed_requested_delivery_date', 'order_allocation', 'flag',
                 'r_type','priority_line_flag', 'units_per_pallet', 'weight_per_unit', 'volume_per_unit',
                 'delivery_date_check_flag',
                 'weight_check_flag', 'volume_check_flag', 'pallet_check_flag', 'base_unit', 'order_creation_date',
                 'order_quantity_unit', 'planned_goods_issue_date',
                 'order_quantity_in_base_unit', 'pallet_spot_conversion_factor', 'materialbycustomer',
                 'shuffle_together_flag', 'scenario_name']]
            output_dict['finial_order_df'] = con_finial_order_df
            logger.info("Order Solution DataFrame Created")

        except Exception as e:
            logger.warning("Order Solution DataFrame missing or empty " + str(e))
            logger.warning(f"Result: {traceback.format_exc()}")
            con_finial_order_df = pd.DataFrame(columns=['scenario_id', 'sales_document', 'sales_document_item', 'schedule_line', 'material',
                         'po_number', 'dc', 'dc_name',
                         'pallet_spot', 'gross_weight', 'confirmed_quantity_in_base_unit', 'volume',
                         'requested_delivery_date', 'atp_availability_date', 'delivery_date', 'original_delivery_date',
                         'actual_delivery_date',
                         'requested_delivery_period', 'delivery_period', 'requested_delivery_day_name',
                         'delivery_day_name',
                         'proposed_po', 'proposed_period', 'proposed_requested_delivery_date', 'order_allocation',
                         'flag', 'r_type',
                         'priority_line_flag', 'units_per_pallet', 'weight_per_unit', 'volume_per_unit',
                         'delivery_date_check_flag',
                         'weight_check_flag', 'volume_check_flag', 'pallet_check_flag', 'base_unit',
                         'order_creation_date', 'order_quantity_unit', 'planned_goods_issue_date',
                         'order_quantity_in_base_unit', 'pallet_spot_conversion_factor', 'materialbycustomer',
                         'shuffle_together_flag', 'scenario_name'])
            output_dict['finial_order_df'] = con_finial_order_df
            logger.warning("Order Solution DataFrame Empty")

        # Truck DataFrame
        try:
            logger.info("Creating Truck Details DataFrame")

            if len(self.truck_details_fully_utilized) > 0:
                con_truck_df = pd.concat([self.input_data_dict['truck_capacity_details'], self.truck_details_fully_utilized])
            else:
                con_truck_df = self.input_data_dict['truck_capacity_details'].copy()
            con_truck_df = con_truck_df.reset_index(drop=True)

            fully_utilized = con_finial_order_df.groupby(['dc', 'po_number', 'requested_delivery_date', 'proposed_period', 'flag']).agg({'gross_weight': 'sum', 'volume': 'sum', 'pallet_spot': 'sum'}).reset_index()
            fully_utilized = pd.merge(fully_utilized, con_truck_df, how='left',on=['dc', 'po_number', 'requested_delivery_date'])
            fully_utilized = fully_utilized[['dc', 'po_number', 'requested_delivery_date', 'proposed_period', 'flag', 'gross_weight', 'volume',
                 'pallet_spot', 'pallet_constraint', 'weight_constraint', 'volume_constraint']]

            fully_utilized = fully_utilized.rename(columns={'requested_delivery_date': 'date', 'proposed_period': 'period', 'gross_weight': 'weight_used',
                         'volume': 'volume_used','pallet_spot': 'pallet_used', 'weight_constraint': 'weight_limit',
                         'volume_constraint': 'volume_limit', 'pallet_constraint': 'pallet_limit'})
            fully_utilized['original_period'] = fully_utilized['period']
            fully_utilized['original_date'] = fully_utilized['date']
            fully_utilized['original_weight_used'] = fully_utilized['weight_used']
            fully_utilized['original_volume_used'] = fully_utilized['volume_used']
            fully_utilized['original_pallet_used'] = fully_utilized['pallet_used']
            fully_utilized['truck_selection'] = 1
            fully_utilized['unused_weight'] = fully_utilized['weight_limit'] - fully_utilized['weight_used']
            fully_utilized['unused_volume'] = fully_utilized['volume_limit'] - fully_utilized['volume_used']
            fully_utilized['unused_pallet'] = fully_utilized['pallet_limit'] - fully_utilized['pallet_used']
            fully_utilized['unused_weight_percent'] = (fully_utilized['weight_limit'] - fully_utilized['weight_used']) / \
                                                      fully_utilized['weight_limit']
            fully_utilized['unused_volume_percent'] = (fully_utilized['volume_limit'] - fully_utilized['volume_used']) / \
                                                      fully_utilized['volume_limit']
            fully_utilized['unused_pallet_percent'] = (fully_utilized['pallet_limit'] - fully_utilized['pallet_used']) / \
                                                      fully_utilized['pallet_limit']
            fully_utilized['scenario_id'] = self.plan_id
            fully_utilized = fully_utilized[['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period', 'original_date',
                 'truck_selection',
                 'weight_limit', 'volume_limit', 'pallet_limit', 'original_weight_used', 'weight_used',
                 'original_volume_used', 'volume_used',
                 'original_pallet_used', 'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet',
                 'unused_weight_percent',
                 'unused_volume_percent', 'unused_pallet_percent', 'flag']]
            output_dict['truck_df'] = fully_utilized

            # Filtered Dataframe
            selected_df = fully_utilized.copy()
            selected_df['action'] = 'Selected'
            selected_df['scenario_name'] = 'DirectlyFromInput'
            selected_df = selected_df[['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period', 'original_date',
                 'truck_selection', 'weight_limit', 'volume_limit',
                 'pallet_limit', 'original_weight_used', 'weight_used', 'original_volume_used', 'volume_used',
                 'original_pallet_used',
                 'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet', 'unused_weight_percent',
                 'unused_volume_percent',
                 'unused_pallet_percent', 'flag', 'action', 'scenario_name']]
            output_dict['sel_non_sel_df'] = selected_df

            logger.info("Truck Details Solution DataFrame Created")

        except Exception as e:
            logger.warning("Truck Details Solution DataFrame missing or empty " + str(e))
            logger.warning(f"Result: {traceback.format_exc()}")
            fully_utilized = pd.DataFrame(columns=['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period', 'original_date',
                         'truck_selection',
                         'weight_limit', 'volume_limit', 'pallet_limit', 'original_weight_used', 'weight_used',
                         'original_volume_used', 'volume_used',
                         'original_pallet_used', 'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet',
                         'unused_weight_percent',
                         'unused_volume_percent', 'unused_pallet_percent', 'truck_under_utilization',
                         'truck_under_utilization_range_trigger', 'unused_weight_percent_solver',
                         'unused_volume_percent_solver', 'unused_pallet_percent_solver', 'flag'])

            selected_df = pd.DataFrame(columns=['scenario_id', 'dc', 'po_number', 'period', 'date', 'original_period', 'original_date',
                         'truck_selection', 'weight_limit', 'volume_limit',
                         'pallet_limit', 'original_weight_used', 'weight_used', 'original_volume_used', 'volume_used',
                         'original_pallet_used',
                         'pallet_used', 'unused_weight', 'unused_volume', 'unused_pallet', 'unused_weight_percent',
                         'unused_volume_percent',
                         'unused_pallet_percent', 'truck_under_utilization', 'truck_under_utilization_range_trigger',
                         'unused_weight_percent_solver',
                         'unused_volume_percent_solver', 'unused_pallet_percent_solver', 'flag', 'action',
                         'scenario_name'])
            output_dict['truck_df'] = fully_utilized
            output_dict['sel_non_sel_df'] = selected_df
            logger.warning("Truck Details Solution DataFrame Empty")

        return output_dict